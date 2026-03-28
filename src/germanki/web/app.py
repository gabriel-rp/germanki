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
from germanki.chatgpt import WEB_UI_CHATGPT_PROMPT, ChatGPTAPI
from germanki.config import Config
from germanki.core import AnkiCardCreator, AnkiCardInfo, Germanki
from germanki.photos.pexels import PexelsClient
from germanki.photos.unsplash import UnsplashClient
from germanki.static import input_examples
from germanki.utils import get_logger
from germanki.web.session import SessionManager, UserSession

logger = get_logger(__file__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB
    await SessionManager.initialize()
    yield


app: Final[FastAPI] = FastAPI(lifespan=lifespan)

# Setup paths
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
TEMPLATES_DIR: Final[Path] = BASE_DIR / 'templates'
STATIC_DIR: Final[Path] = BASE_DIR / 'static'
GERMANKI_ROOT: Final[Path] = Path(germanki_file).parent

# Mount static files
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
config = Config()
app.mount(
    '/media/audio',
    StaticFiles(directory=config.audio_downloads_folder),
    name='audio',
)
app.mount(
    '/media/image',
    StaticFiles(directory=config.image_downloads_folder),
    name='image',
)

templates: Final[Jinja2Templates] = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)
templates.env.filters['basename'] = lambda p: Path(p).name if p else ''


def get_noun_color(extra: str | None) -> str | None:
    if not extra:
        return None
    first_word = extra.strip().split()[0].lower()
    if first_word == 'der':
        return 'blue'
    elif first_word == 'die':
        return 'red'
    elif first_word == 'das':
        return 'black'
    return None


templates.env.filters['noun_color'] = get_noun_color


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

    if session.photo_source == 'unsplash':
        client = UnsplashClient(cfg.unsplash_api_key)
    else:
        client = PexelsClient(cfg.pexels_api_key)

    service = Germanki(photos_client=client, config=cfg)
    service.selected_speaker = session.selected_speaker
    return service


@app.get('/', response_class=HTMLResponse)
async def read_root(
    request: Request, session: UserSession = Depends(get_session)
):
    manual_example_path = Path(input_examples.__file__).parent / 'default.yaml'
    manual_example = (
        manual_example_path.read_text() if manual_example_path.exists() else ''
    )
    chatgpt_example = 'Hund\nKatze\n'

    service = get_germanki_service(session)

    # Fetch Anki decks
    from germanki.anki_connect import AnkiConnectClient

    anki_client = AnkiConnectClient()
    try:
        anki_decks = await anki_client.get_deck_names()
    except Exception:
        anki_decks = []

    response = templates.TemplateResponse(
        'index.html',
        {
            'request': request,
            'cards': session.cards,
            'deck_name': session.deck_name,
            'anki_decks': anki_decks,
            'speaker': session.selected_speaker,
            'input_source': session.input_source,
            'photo_source': session.photo_source,
            'enable_images': session.enable_images,
            'chatgpt_prompt': WEB_UI_CHATGPT_PROMPT,
            'manual_example': manual_example,
            'chatgpt_example': chatgpt_example,
            'openai_key_set': bool(service.config.openai_api_key),
            'pexels_key_set': bool(
                service.config.pexels_api_key
                or service.config.unsplash_api_key
            )
            if session.enable_images
            else True,
        },
    )
    response.set_cookie(key='session_id', value=session.session_id)
    return response


@app.post('/generate', response_class=HTMLResponse)
async def generate_cards(
    request: Request,
    input_text: str = Form(...),
    input_source: str = Form('chatgpt'),
    photo_source: str = Form('pexels'),
    enable_images: str | None = Form(None),
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    session.input_source = input_source
    session.photo_source = photo_source
    session.enable_images = enable_images == 'on'

    try:
        if input_source == 'chatgpt':
            if not service.config.openai_api_key:
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>OpenAI API Key missing!</strong><br>
                    Please add your key in Settings to use ChatGPT generation.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )
            chatgpt = ChatGPTAPI(service.config.openai_api_key)
            collection = await chatgpt.query(input_text)
            new_cards = collection.card_contents
        else:
            import yaml

            data = yaml.safe_load(input_text)
            new_cards = [AnkiCardInfo(**item) for item in data]

        if session.enable_images:
            if photo_source == 'pexels' and not service.config.pexels_api_key:
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>Pexels API Key missing!</strong><br>
                    Please add your key in Settings to use Pexels images.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )
            if (
                photo_source == 'unsplash'
                and not service.config.unsplash_api_key
            ):
                return HTMLResponse(
                    content="""
                 <div class='error' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>
                    <strong>Unsplash API Key missing!</strong><br>
                    Please add your key in Settings to use Unsplash images.
                    <button class='outline' onclick="document.getElementById('settings-modal').showModal()">Open Settings</button>
                 </div>
                 """
                )

        session.cards = new_cards
        media_errors = await service.populate_media(
            session.cards, skip_images=not session.enable_images
        )
        await SessionManager.save_session(session)

        error_html = ''
        if media_errors:
            error_html = "<div class='warning' style='margin-bottom: 1rem; padding: 0.5rem; border: 2px solid var(--border-color); background: var(--card-bg);'>"
            error_html += "<strong>⚠️ Some media failed to load:</strong><ul style='font-size: 0.8rem; margin: 0.5rem 0 0 1rem;'>"
            for err in media_errors:
                error_html += f'<li>{str(err)}</li>'
            error_html += '</ul></div>'

        card_list_html = templates.get_template(
            'partials/card_list.html'
        ).render({'request': request, 'cards': session.cards})

        return HTMLResponse(content=error_html + card_list_html)
    except Exception as e:
        return HTMLResponse(
            content=f"<div class='error' style='padding: 1rem; border: 2px solid #ff0000; background: #fff1f0; color: #ff0000;'><strong>❌ Error:</strong> {str(e)}</div>"
        )


@app.post('/update-card/{index}/image')
async def update_image(
    request: Request,
    index: int,
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    if 0 <= index < len(session.cards):
        if (
            session.photo_source == 'pexels'
            and not service.config.pexels_api_key
        ):
            return HTMLResponse(
                content=f"<div class='error' id='card-{index}' style='padding: 0.5rem; background: var(--card-bg); border: 1px solid var(--border-color);'>Pexels API Key missing!</div>"
            )
        if (
            session.photo_source == 'unsplash'
            and not service.config.unsplash_api_key
        ):
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
            'partials/card_preview.html',
            {'request': request, 'card': card, 'index': index},
        )
    return HTMLResponse(content='')


@app.post('/update-card/{index}/audio')
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
            'partials/card_preview.html',
            {'request': request, 'card': card, 'index': index},
        )
    return HTMLResponse(content='')


@app.post('/create-cards')
async def create_cards_anki(
    request: Request,
    deck_name: str = Form(...),
    force_update: str | None = Form(None),
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    should_force = force_update == 'on'
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
            logger.error(f'Error checking model status: {e}')

    try:
        responses = await service.create_cards(
            templates.env, session.cards, deck_name, force_update=should_force
        )
        errors = [r.exception for r in responses if r.exception]
        if errors:
            error_msg = f"<div class='warning' style='padding: 1rem; border: 2px solid var(--border-color); background: var(--card-bg);'>"
            error_msg += f"<strong>⚠️ Created with {len(errors)} errors:</strong><ul style='font-size: 0.8rem; margin-top: 0.5rem;'>"
            for err in errors:
                error_msg += f'<li>{str(err)}</li>'
            error_msg += '</ul></div>'
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


@app.post('/settings')
async def update_settings(
    request: Request,
    openai_key: str | None = Form(None),
    pexels_key: str | None = Form(None),
    unsplash_key: str | None = Form(None),
    speaker: str | None = Form(None),
    session: UserSession = Depends(get_session),
):
    if openai_key is not None:
        session.openai_api_key = openai_key
    if pexels_key is not None:
        session.pexels_api_key = pexels_key
    if unsplash_key is not None:
        session.unsplash_api_key = unsplash_key
    if speaker is not None:
        session.selected_speaker = speaker

    await SessionManager.save_session(session)
    service = get_germanki_service(session)

    response_content = templates.get_template(
        'partials/status_banner.html'
    ).render(
        {
            'request': request,
            'openai_key_set': bool(service.config.openai_api_key),
            'pexels_key_set': bool(
                service.config.pexels_api_key
                or service.config.unsplash_api_key
            )
            if session.enable_images
            else True,
        }
    )
    response_content += "<div class='success'>Settings updated</div>"
    return HTMLResponse(content=response_content)
