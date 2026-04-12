import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from germanki import __file__ as germanki_file
from germanki.llm import WEB_UI_LLM_PROMPT, LLMAPI
from germanki.config import Config
from germanki.core import AnkiCardCreator, AnkiCardInfo, Germanki
from germanki.photos.pexels import PexelsClient
from germanki.photos.unsplash import UnsplashClient
from germanki.static import input_examples
from germanki.utils import get_logger
from germanki.web.session import SessionManager, UserSession
from germanki.web.templates import get_templates

# Setup paths
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
STATIC_DIR: Final[Path] = BASE_DIR / "static"
GERMANKI_ROOT: Final[Path] = Path(germanki_file).parent

logger = get_logger(__file__)
templates = get_templates(BASE_DIR)
config = Config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB
    await SessionManager.initialize()
    yield


app: Final[FastAPI] = FastAPI(lifespan=lifespan)
# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount(
    "/media/audio",
    StaticFiles(directory=config.audio_downloads_folder),
    name="audio",
)
app.mount(
    "/media/image",
    StaticFiles(directory=config.image_downloads_folder),
    name="image",
)


async def get_session(session_id: str | None = Cookie(None)) -> UserSession:
    if not session_id:
        session_id = await SessionManager.create_session()
    return await SessionManager.get_session(session_id)


def get_germanki_service(
    session: UserSession = Depends(get_session),
) -> Germanki:
    cfg = Config()
    if session.pexels_api_key:
        cfg.pexels_api_key = session.pexels_api_key
    if session.unsplash_api_key:
        cfg.unsplash_api_key = session.unsplash_api_key
    if session.openai_api_key:
        cfg.openai_api_key = session.openai_api_key

    if session.photo_source == "unsplash":
        client = UnsplashClient(cfg.unsplash_api_key)
    else:
        client = PexelsClient(cfg.pexels_api_key)

    service = Germanki(
        photos_client=client, config=cfg, selected_speaker=session.selected_speaker
    )
    return service


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, session: UserSession = Depends(get_session)):
    manual_example_path = Path(input_examples.__file__).parent / "default.yaml"
    manual_example = (
        manual_example_path.read_text() if manual_example_path.exists() else ""
    )
    llm_example = "Hund\nKatze\n"

    service = get_germanki_service(session)

    # Fetch Anki decks
    from germanki.anki_connect import AnkiConnectClient

    anki_client = AnkiConnectClient()
    try:
        anki_decks = await anki_client.get_deck_names()
    except Exception:
        anki_decks = []

    response = templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cards": session.cards,
            "input_text": session.input_text,
            "deck_name": session.deck_name,
            "anki_decks": anki_decks,
            "speaker": session.selected_speaker,
            "llm_model": session.llm_model,
            "input_source": session.input_source,
            "photo_source": session.photo_source,
            "enable_images": session.enable_images,
            "llm_prompt": WEB_UI_LLM_PROMPT,
            "manual_example": manual_example,
            "llm_example": llm_example,
            "openai_key_set": bool(service.config.openai_api_key),
            "pexels_key_set": bool(
                service.config.pexels_api_key or service.config.unsplash_api_key
            )
            if session.enable_images
            else True,
        },
    )
    response.set_cookie(key="session_id", value=session.session_id)
    return response


@app.post("/generate", response_class=HTMLResponse)
async def generate_cards(
    request: Request,
    input_text: str = Form(...),
    input_source: str = Form("chatgpt"),
    photo_source: str = Form("pexels"),
    enable_images: str | None = Form(None),
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    session.input_source = input_source
    session.input_text = input_text
    session.photo_source = photo_source
    session.enable_images = enable_images == "on"

    try:
        if input_source == "chatgpt":
            if not service.config.openai_api_key:
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>LLM API Key missing!</strong><br>
                    Please add your key in Settings to use LLM generation.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )

            # Split input into lines and normalize
            input_lines = [
                line.strip() for line in input_text.split("\n") if line.strip()
            ]

            # Identify which lines are NOT represented in session.cards
            # This handles the "only new cards" requirement.
            new_lines = []
            for line in input_lines:
                found = False
                l_lower = line.lower()
                for card in session.cards:
                    c_lower = card.word.lower()
                    # Fuzzy match: input line is in card word or vice versa (e.g. "hund" vs "Hund")
                    if l_lower == c_lower or l_lower in c_lower or c_lower in l_lower:
                        found = True
                        break
                if not found:
                    new_lines.append(line)

            if new_lines:
                llm = LLMAPI(
                    api_key=service.config.openai_api_key, model=session.llm_model
                )
                collection = await llm.query("\n".join(new_lines))
                # Append only truly new cards
                session.cards.extend(collection.card_contents)

            # Filter session.cards to only keep those whose word matches a line in input_text
            # This handles the "deletions in input area" case.
            final_cards = []
            for card in session.cards:
                c_lower = card.word.lower()
                for line in input_lines:
                    l_lower = line.lower()
                    if l_lower == c_lower or l_lower in c_lower or c_lower in l_lower:
                        final_cards.append(card)
                        break
            session.cards = final_cards
            new_cards_added = collection.card_contents if new_lines else []
        else:
            import yaml

            data = yaml.safe_load(input_text)
            new_cards_added = [AnkiCardInfo(**item) for item in data]
            session.cards = new_cards_added

        if session.enable_images:
            # ... rest of the image logic ...
            if photo_source == "pexels" and not service.config.pexels_api_key:
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>Pexels API Key missing!</strong><br>
                    Please add your key in Settings to use Pexels images.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )
            if photo_source == "unsplash" and not service.config.unsplash_api_key:
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>Unsplash API Key missing!</strong><br>
                    Please add your key in Settings to use Unsplash images.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )

        media_errors = await service.populate_media(
            new_cards_added, skip_images=not session.enable_images
        )
        await SessionManager.save_session(session)

        error_html = ""
        if media_errors:
            error_html = "<div class='warning' style='margin-bottom: 1rem; padding: 0.5rem; border: 2px solid var(--border-color); background: var(--card-bg);'>"
            error_html += "<strong>⚠️ Some media failed to load:</strong><ul style='font-size: 0.8rem; margin: 0.5rem 0 0 1rem;'>"
            for err in media_errors:
                error_html += f"<li>{str(err)}</li>"
            error_html += "</ul></div>"

        card_list_html = templates.get_template("partials/card_list.html").render(
            {"request": request, "cards": session.cards}
        )

        return HTMLResponse(content=error_html + card_list_html)
    except Exception as e:
        return HTMLResponse(
            content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Error:</strong> {str(e)}</div>"
        )


@app.post("/save-input")
async def save_input(
    input_text: str = Form(...),
    session: UserSession = Depends(get_session),
):
    session.input_text = input_text
    await SessionManager.save_session(session)
    return Response(status_code=204)


@app.post('/clear-cards')
async def clear_cards(
    session: UserSession = Depends(get_session),
):
    session.cards = []
    session.input_text = ''
    await SessionManager.save_session(session)
    return HTMLResponse(
        content="""
        <div style='border: 2px dashed var(--border-color); padding: 3rem; text-align: center; background: var(--card-bg); width: 100%; border-radius: var(--border-radius);'>
            <p style='font-weight: bold; color: var(--text-main); opacity: 0.5;'>EMPTY</p>
        </div>
        <script>document.getElementById('input-text').value = '';</script>
        """
    )


@app.post('/clear-media')
async def clear_media(
    service: Germanki = Depends(get_germanki_service),
):
    import shutil

    # Clear audio and image folders
    for folder in [
        service.config.audio_downloads_folder,
        service.config.image_downloads_folder,
    ]:
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    return "<div class='success'>Media cache cleared!</div>"



@app.post("/update-card/{index}/image")
async def update_image(
    request: Request,
    index: int,
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    if 0 <= index < len(session.cards):
        if session.photo_source == "pexels" and not service.config.pexels_api_key:
            return HTMLResponse(
                content=f"<div class='error' id='card-{index}' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'>Pexels API Key missing!</div>"
            )
        if session.photo_source == "unsplash" and not service.config.unsplash_api_key:
            return HTMLResponse(
                content=f"<div class='error' id='card-{index}' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'>Unsplash API Key missing!</div>"
            )

        card = session.cards[index]
        try:
            await service.update_card_image(card)
            await SessionManager.save_session(session)
        except Exception as e:
            return HTMLResponse(
                content=f"<div class='error' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'><strong>❌ Image update failed:</strong> {str(e)}</div>"
            )

        return templates.TemplateResponse(
            "partials/card_preview.html",
            {"request": request, "card": card, "index": index},
        )
    return HTMLResponse(content="")


@app.post("/update-card/{index}/audio")
async def update_audio(
    request: Request,
    index: int,
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    if 0 <= index < len(session.cards):
        card = session.cards[index]
        try:
            await service.update_card_audio(card)
            await SessionManager.save_session(session)
        except Exception as e:
            return HTMLResponse(
                content=f"<div class='error' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'><strong>❌ Audio update failed:</strong> {str(e)}</div>"
            )

        return templates.TemplateResponse(
            "partials/card_preview.html",
            {"request": request, "card": card, "index": index},
        )
    return HTMLResponse(content="")


@app.post("/update-card/{index}/content")
async def update_card_content(
    request: Request,
    index: int,
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    if 0 <= index < len(session.cards):
        if not service.config.openai_api_key:
            return HTMLResponse(
                content=f"<div class='error' id='card-{index}' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'>LLM API Key missing!</div>"
            )

        card = session.cards[index]
        original_word = card.word
        # If it contains extra info like "+ akk.", try to strip it for the query if it helps,
        # but LLM is usually smart enough. Let's just use what's there or the original user input?
        # The card.word might already be processed.

        try:
            llm = LLMAPI(api_key=service.config.openai_api_key, model=session.llm_model)
            new_card_info = await llm.query_single_card(original_word)

            # Preserve existing media and speaker
            new_card_info.speaker = card.speaker
            new_card_info.word_audio_url = card.word_audio_url
            new_card_info.translation_image_url = card.translation_image_url

            session.cards[index] = new_card_info
            await SessionManager.save_session(session)
        except Exception as e:
            return HTMLResponse(
                content=f"<div class='error' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'><strong>❌ Content refresh failed:</strong> {str(e)}</div>"
            )

        return templates.TemplateResponse(
            "partials/card_preview.html",
            {"request": request, "card": new_card_info, "index": index},
        )
    return HTMLResponse(content="")


@app.post("/create-cards")
async def create_cards_anki(
    request: Request,
    deck_name: str = Form(...),
    force_update: str | None = Form(None),
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    should_force = force_update == "on"
    session.deck_name = deck_name
    await SessionManager.save_session(session)

    from germanki.anki_connect import AnkiConnectClient

    anki_client = AnkiConnectClient()

    # Check if model is outdated
    if not should_force:
        try:
            if await service.check_model_outdated(anki_client):
                return """
                <div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'>
                    <strong>❌ Template Update Required</strong><br>
                    The GermAnki template in Anki is outdated. Please check the <strong>"ACCEPT TEMPLATE UPDATES"</strong> box above to proceed.
                    <br><small>Note: This will update existing cards to the new layout.</small>
                </div>
                """
        except Exception as e:
            logger.error(f"Error checking model status: {e}")

    try:
        responses = await service.create_cards(
            templates.env, session.cards, deck_name, force_update=should_force
        )
        errors = [r.exception for r in responses if r.exception]
        if errors:
            error_msg = f"<div class='warning' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>"
            error_msg += f"<strong>⚠️ Created with {len(errors)} errors:</strong><ul style='font-size: 0.8rem; margin-top: 0.5rem;'>"
            for err in errors:
                error_msg += f"<li>{str(err)}</li>"
            error_msg += "</ul></div>"
            return HTMLResponse(content=error_msg)
        return HTMLResponse(
            content="<div class='success' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'><strong>✅ Cards created successfully!</strong></div>"
        )
    except Exception as e:
        from germanki.anki_connect import AnkiConnectRequestError

        if isinstance(e, AnkiConnectRequestError):
            return HTMLResponse(
                content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Connection failed:</strong> {str(e)}<br><p style='margin-top: 0.5rem; font-size: 0.8rem;'>Please ensure Anki is running and the AnkiConnect add-on is installed.</p></div>"
            )
        return HTMLResponse(
            content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Error creating cards:</strong> {str(e)}</div>"
        )


@app.post("/settings")
async def update_settings(
    request: Request,
    openai_key: str | None = Form(None),
    llm_model: str | None = Form(None),
    pexels_key: str | None = Form(None),
    unsplash_key: str | None = Form(None),
    speaker: str | None = Form(None),
    session: UserSession = Depends(get_session),
):
    if openai_key is not None:
        session.openai_api_key = openai_key
    if llm_model is not None:
        session.llm_model = llm_model
    if pexels_key is not None:
        session.pexels_api_key = pexels_key
    if unsplash_key is not None:
        session.unsplash_api_key = unsplash_key
    if speaker is not None:
        session.selected_speaker = speaker

    await SessionManager.save_session(session)
    service = get_germanki_service(session)

    response_content = templates.get_template("partials/status_banner.html").render(
        {
            "request": request,
            "openai_key_set": bool(service.config.openai_api_key),
            "pexels_key_set": bool(
                service.config.pexels_api_key or service.config.unsplash_api_key
            )
            if session.enable_images
            else True,
        }
    )
    response_content += "<div class='success'>Settings updated</div>"
    return HTMLResponse(content=response_content)
