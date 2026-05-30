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
from fastapi.responses import HTMLResponse, StreamingResponse
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
    llm_example = "Hünd\nHunde\nging\nschnellere\nden Löffel abgeben\n"

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


@app.post("/generate")
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

    async def generate_stream():
        try:
            # 1. Start: Disable UI and Clear list using OOB
            yield "<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'></div>"
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = true;</script>"

            if input_source == "chatgpt":
                if not service.config.openai_api_key:
                    yield "<div id='card-list' hx-swap-oob='true'><div class='error'>API Key missing</div></div>"
                    yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"
                    return

                input_lines = [line.strip() for line in input_text.split("\n") if line.strip()]
                
                # Filter session cards
                new_session_cards = []
                for card in session.cards:
                    if any(line.lower() in card.word.lower() or card.word.lower() in line.lower() for line in input_lines):
                        new_session_cards.append(card)
                session.cards = new_session_cards

                # Identify truly new lines
                new_lines = []
                for line in input_lines:
                    if not any(line.lower() in card.word.lower() or card.word.lower() in line.lower() for card in session.cards):
                        new_lines.append(line)

                # Show existing cards first
                if session.cards:
                    existing_html = ""
                    for i, card in enumerate(session.cards):
                        card_inner = templates.get_template("partials/card_preview.html").render(
                            {"request": request, "card": card, "index": i}
                        )
                        existing_html += f"<li id='card-item-{i}'>{card_inner}</li>"
                    yield f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{existing_html}</div>"

                if new_lines:
                    llm = LLMAPI(api_key=service.config.openai_api_key, model=session.llm_model)
                    
                    async for batch_cards in llm.query("\n".join(new_lines)):
                        await service.populate_media(batch_cards, skip_images=not session.enable_images)
                        
                        for card in batch_cards:
                            curr_idx = len(session.cards)
                            session.cards.append(card)
                            await SessionManager.save_session(session)
                            
                            card_inner = templates.get_template("partials/card_preview.html").render(
                                {"request": request, "card": card, "index": curr_idx}
                            )
                            # Append using beforeend swap on the list
                            yield f"<div id='card-list' hx-swap-oob='beforeend'><li id='card-item-{curr_idx}'>{card_inner}</li></div>"

            else:
                import yaml
                data = yaml.safe_load(input_text)
                session.cards = [AnkiCardInfo(**item) for item in data]
                await service.populate_media(session.cards, skip_images=not session.enable_images)
                await SessionManager.save_session(session)
                
                all_html = ""
                for i, card in enumerate(session.cards):
                    card_inner = templates.get_template("partials/card_preview.html").render(
                        {"request": request, "card": card, "index": i}
                    )
                    all_html += f"<li id='card-item-{i}'>{card_inner}</li>"
                yield f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{all_html}</div>"

            # Finalize: enable sync button
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"<div id='card-list' hx-swap-oob='beforeend'><div class='error'><strong>❌ Error:</strong> {str(e)}</div></div>"
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"

    return StreamingResponse(generate_stream(), media_type="text/html")


@app.post("/save-input")
async def save_input(
    input_text: str = Form(...),
    session: UserSession = Depends(get_session),
):
    session.input_text = input_text
    await SessionManager.save_session(session)
    return Response(status_code=204)


@app.post("/check-duplicates")
async def check_duplicates(
    input_text: str = Form(...),
    deck_name: str = Form(...),
):
    from germanki.anki_connect import AnkiConnectClient
    anki_client = AnkiConnectClient()
    
    words = [line.strip() for line in input_text.split('\n') if line.strip()]
    if not words:
        return HTMLResponse(content="")

    duplicates = []
    try:
        # We search for existing notes in the specified deck that have the word in the 'Front' field.
        # Anki search syntax: 'deck:"Deck Name" "Front:Word"'
        for word in words:
            # Simple check first - exact match on Front field
            query = f'deck:"{deck_name}" "Front:{word}"'
            found = await anki_client.find_notes(query)
            if found:
                duplicates.append(word)
    except Exception as e:
        logger.error(f"Error checking duplicates: {e}")
        return HTMLResponse(content="")

    if duplicates:
        dup_list = ", ".join(duplicates)
        return HTMLResponse(
            content=f"""
            <div class='warning' style='margin-bottom: 1rem; padding: 0.75rem; border: 2px solid #ffcc00; background: #fffde6; color: #856404; font-size: 0.8rem; border-radius: var(--border-radius);'>
                <strong>⚠️ Already in Anki:</strong> {dup_list}
            </div>
            """
        )
    
    return HTMLResponse(content="")


@app.post('/clear-cards')
async def clear_cards(
    session: UserSession = Depends(get_session),
):
    session.cards = []
    session.input_text = ''
    await SessionManager.save_session(session)
    return HTMLResponse(
        content="""
        <ul id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>
            <div id='empty-state' style='grid-column: 1 / -1; border: 2px dashed var(--border-color); padding: 3rem; text-align: center; background: var(--card-bg); width: 100%; border-radius: var(--border-radius);'>
                <p style='font-weight: bold; color: var(--text-main); opacity: 0.5;'>EMPTY</p>
            </div>
        </ul>
        <script>document.getElementById('input-text').value = '';</script>
        """
    )


@app.post("/delete-card/{index}")
async def delete_card(
    request: Request,
    index: int,
    session: UserSession = Depends(get_session),
):
    if 0 <= index < len(session.cards):
        removed_card = session.cards.pop(index)

        # Also remove from input_text to prevent re-generation
        word_to_remove = removed_card.word.lower()
        lines = session.input_text.split('\n')
        new_lines = []
        for line in lines:
            l_strip = line.strip()
            if not l_strip:
                continue
            l_lower = l_strip.lower()
            # If the line matches the removed word, skip it
            if l_lower == word_to_remove or l_lower in word_to_remove or word_to_remove in l_lower:
                continue
            new_lines.append(line)

        session.input_text = '\n'.join(new_lines)
        await SessionManager.save_session(session)
        
        # Re-render the whole list to ensure indices are correct
        card_list_html = templates.get_template("partials/card_list.html").render(
            {"request": request, "cards": session.cards}
        )
        
        # If no cards left, show empty state
        if not session.cards:
            card_list_html = """
            <ul id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>
                <div id='empty-state' style='grid-column: 1 / -1; border: 2px dashed var(--border-color); padding: 3rem; text-align: center; background: var(--card-bg); width: 100%; border-radius: var(--border-radius);'>
                    <p style='font-weight: bold; color: var(--text-main); opacity: 0.5;'>EMPTY</p>
                </div>
            </ul>
            """
        else:
            # Wrap in hx-swap-oob for card-list
            card_list_html = f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{card_list_html}</div>"

        import json
        return HTMLResponse(
            content=card_list_html, 
            headers={
                "HX-Trigger": json.dumps({
                    "card-deleted": session.input_text
                })
            }
        )

    return HTMLResponse(content="")


@app.post("/clear-media")
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

        # Wrap in <li> to match new structure
        inner_html = templates.get_template("partials/card_preview.html").render(
            {"request": request, "card": card, "index": index}
        )
        return HTMLResponse(content=inner_html)
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

        inner_html = templates.get_template("partials/card_preview.html").render(
            {"request": request, "card": card, "index": index}
        )
        return HTMLResponse(content=inner_html)
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

        inner_html = templates.get_template("partials/card_preview.html").render(
            {"request": request, "card": new_card_info, "index": index}
        )
        return HTMLResponse(content=inner_html)
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
        
        # Track which words were successful to clean them from input_text
        successful_words = []
        remaining_cards = []
        
        for response, card in zip(responses, session.cards):
            if response.exception:
                card.creation_error = str(response.exception)
                remaining_cards.append(card)
            else:
                successful_words.append(card.word.lower())

        # Update session cards to only include failed ones
        session.cards = remaining_cards
        
        # Update input_text to only include failed words
        if successful_words:
            lines = session.input_text.split('\n')
            new_lines = []
            for line in lines:
                l_strip = line.strip()
                if not l_strip:
                    continue
                if l_strip.lower() not in successful_words:
                    new_lines.append(line)
            session.input_text = '\n'.join(new_lines)

        await SessionManager.save_session(session)

        # Prepare UI response
        card_list_html = templates.get_template("partials/card_list.html").render(
            {"request": request, "cards": session.cards}
        )
        
        # If no cards left, show empty state
        if not session.cards:
            card_list_html = """
            <ul id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>
                <div id='empty-state' style='grid-column: 1 / -1; border: 2px dashed var(--border-color); padding: 3rem; text-align: center; background: var(--card-bg); width: 100%; border-radius: var(--border-radius);'>
                    <p style='font-weight: bold; color: var(--text-main); opacity: 0.5;'>EMPTY</p>
                </div>
            </ul>
            """
        else:
             card_list_html = f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{card_list_html}</div>"

        import json
        headers = {
            "HX-Trigger": json.dumps({
                "card-deleted": session.input_text, # Re-use existing trigger to update textarea
                "sync-finished": "success" if not remaining_cards else "warning"
            })
        }
        
        # Add a status banner at the top of the list if there were errors
        if remaining_cards:
            status_banner = f"<div class='warning' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg); margin-bottom: 1rem;'><strong>⚠️ Sync encountered errors.</strong> Successfully added {len(successful_words)} cards. {len(remaining_cards)} cards failed and are shown below.</div>"
            return HTMLResponse(content=status_banner + card_list_html, headers=headers)
        
        success_msg = f"<div class='success' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg); margin-bottom: 1rem;'><strong>✅ All {len(successful_words)} cards created successfully!</strong></div>"
        return HTMLResponse(content=success_msg + card_list_html, headers=headers)

    except Exception as e:
        from germanki.anki_connect import AnkiConnectRequestError

        if isinstance(e, AnkiConnectRequestError):
            return HTMLResponse(
                content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Connection failed:</strong> {str(e)}<br><p style='margin-top: 0.5rem; font-size: 0.8rem;'>Please ensure Anki is running and the AnkiConnect add-on is installed.</p></div>"
            )
        return HTMLResponse(
            content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Error creating cards:</strong> {str(e)}</div>"
        )


@app.get("/export-cards")
async def export_cards(
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    if not session.cards:
        raise HTTPException(status_code=400, detail="No cards to export")

    try:
        apkg_data = await service.export_cards(templates.env, session.cards, deck_name=session.deck_name)
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Export failed:</strong> {str(e)}</div>",
            status_code=500
        )

    return Response(
        content=apkg_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=germanki_export.apkg"
        },
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
