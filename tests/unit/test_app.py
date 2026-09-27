"""Tests for the logic in `germanki.web.app`.

These target the decisions the routes make - which cards survive a sync, what
gets pruned from the input box, which photo client is built, when work is
refused - and deliberately ignore the HTML the routes wrap that logic in.
Asserting on markup here would turn every styling tweak into a test failure.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from germanki.anki_connect import (
    AnkiConnectRequestError,
    AnkiConnectResponseError,
)
from germanki.config import Config
from germanki.core import AnkiCardInfo, CreateCardResponse, Germanki
from germanki.photos.pexels import PexelsClient
from germanki.photos.unsplash import UnsplashClient
from germanki.web.app import app, get_germanki_service, get_session
from germanki.web.session import SessionManager, UserSession


def make_card(word: str, **overrides) -> AnkiCardInfo:
    defaults = dict(
        word=word,
        translations=[f'{word}-en'],
        definition='definition',
        examples=['example'],
        extra='extra',
    )
    defaults.update(overrides)
    return AnkiCardInfo(**defaults)


@pytest.fixture(autouse=True)
def isolated_sessions():
    """SessionManager keeps sessions in a class-level dict shared by all tests."""
    SessionManager._sessions.clear()
    yield
    SessionManager._sessions.clear()


@pytest.fixture
def tmp_config(tmp_path):
    return Config(
        pexels_api_key='pexels-key',
        openai_api_key='openai-key',
        audio_downloads_folder=tmp_path / 'audio',
        image_downloads_folder=tmp_path / 'image',
    )


@pytest.fixture(autouse=True)
def stub_app_config(tmp_config):
    """`get_germanki_service` builds a fresh `Config()`, which reads a real .env.

    Pin it so results don't depend on whoever's machine runs the suite.
    """
    with patch('germanki.web.app.Config', return_value=tmp_config):
        yield


@pytest.fixture
def session():
    return UserSession(session_id='test-session')


@pytest.fixture
def service(tmp_config):
    """A real Germanki with its I/O methods faked out."""
    svc = Germanki(photos_client=PexelsClient('pexels-key'), config=tmp_config)
    svc.cleanup_card_media = AsyncMock()
    svc.update_card_image = AsyncMock()
    svc.update_card_audio = AsyncMock()
    svc.populate_media = AsyncMock(return_value=[])
    svc.create_cards = AsyncMock(return_value=[])
    svc.check_model_outdated = AsyncMock(return_value=False)
    svc.export_cards = AsyncMock(return_value=b'apkg-bytes')
    return svc


@pytest.fixture
def client(session, service):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_germanki_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def hx_trigger(response) -> dict:
    return json.loads(response.headers['HX-Trigger'])


# --------------------------------------------------------------------------
# get_germanki_service - builds the service every route depends on
# --------------------------------------------------------------------------


def test_service_prefers_session_keys_over_config(session, tmp_config):
    session.pexels_api_key = 'session-pexels'
    session.openai_api_key = 'session-openai'

    service = get_germanki_service(session)

    assert service.config.pexels_api_key == 'session-pexels'
    assert service.config.openai_api_key == 'session-openai'


def test_service_keeps_config_keys_when_session_has_none(session, tmp_config):
    assert session.pexels_api_key is None

    service = get_germanki_service(session)

    assert service.config.pexels_api_key == 'pexels-key'


@pytest.mark.parametrize(
    'photo_source,expected',
    [('pexels', PexelsClient), ('unsplash', UnsplashClient)],
)
def test_service_photo_source_selects_client(session, photo_source, expected):
    session.photo_source = photo_source

    service = get_germanki_service(session)

    assert isinstance(service.photos_client, expected)


def test_service_uses_session_speaker(session):
    session.selected_speaker = 'Hans'

    assert get_germanki_service(session).selected_speaker == 'Hans'


# --------------------------------------------------------------------------
# POST /create-cards - the highest-consequence logic in the app
# --------------------------------------------------------------------------


def test_create_cards_drops_synced_cards_and_keeps_failures(
    client, session, service
):
    """Only cards Anki rejected stay behind, with their error attached."""
    session.cards = [make_card('Hallo'), make_card('Tschuss')]
    session.input_text = 'Hallo\nTschuss'
    service.create_cards.return_value = [
        CreateCardResponse(card_word='Hallo'),
        CreateCardResponse(
            card_word='Tschuss',
            exception=AnkiConnectResponseError('addNote', 'duplicate note'),
        ),
    ]

    response = client.post('/create-cards', data={'deck_name': 'Deck'})

    assert response.status_code == 200
    assert [c.word for c in session.cards] == ['Tschuss']
    assert 'duplicate note' in session.cards[0].creation_error
    # the synced word is pruned from the input box, the failed one is not
    assert session.input_text == 'Tschuss'
    assert hx_trigger(response)['sync-finished'] == 'warning'


def test_create_cards_clears_session_when_all_succeed(client, session, service):
    session.cards = [make_card('Hallo'), make_card('Tschuss')]
    session.input_text = 'Hallo\nTschuss'
    service.create_cards.return_value = [
        CreateCardResponse(card_word='Hallo'),
        CreateCardResponse(card_word='Tschuss'),
    ]

    response = client.post('/create-cards', data={'deck_name': 'Deck'})

    assert session.cards == []
    assert session.input_text == ''
    assert hx_trigger(response)['sync-finished'] == 'success'


def test_create_cards_persists_deck_name(client, session, service):
    session.cards = [make_card('Hallo')]

    client.post('/create-cards', data={'deck_name': 'My Deck'})

    assert session.deck_name == 'My Deck'
    assert service.create_cards.await_args.args[2] == 'My Deck'


def test_create_cards_refuses_when_anki_template_outdated(
    client, session, service
):
    """An outdated template would silently break existing cards - stop first."""
    session.cards = [make_card('Hallo')]
    service.check_model_outdated.return_value = True

    response = client.post('/create-cards', data={'deck_name': 'Deck'})

    assert 'Template Update Required' in response.text
    service.create_cards.assert_not_awaited()
    assert session.cards  # nothing was consumed


def test_create_cards_force_update_bypasses_template_check(
    client, session, service
):
    session.cards = [make_card('Hallo')]
    service.check_model_outdated.return_value = True
    service.create_cards.return_value = [CreateCardResponse(card_word='Hallo')]

    client.post(
        '/create-cards', data={'deck_name': 'Deck', 'force_update': 'on'}
    )

    service.check_model_outdated.assert_not_awaited()
    assert service.create_cards.await_args.kwargs['force_update'] is True


def test_create_cards_proceeds_when_template_check_errors(
    client, session, service
):
    """Anki being unreachable during the check must not block the attempt."""
    session.cards = [make_card('Hallo')]
    service.check_model_outdated.side_effect = RuntimeError('anki offline')
    service.create_cards.return_value = [CreateCardResponse(card_word='Hallo')]

    client.post('/create-cards', data={'deck_name': 'Deck'})

    service.create_cards.assert_awaited_once()


def test_create_cards_explains_connection_failure(client, session, service):
    session.cards = [make_card('Hallo')]
    service.create_cards.side_effect = AnkiConnectRequestError('refused', None)

    response = client.post('/create-cards', data={'deck_name': 'Deck'})

    assert response.status_code == 200
    assert 'Connection failed' in response.text
    assert 'AnkiConnect add-on' in response.text
    # cards survive so the user can retry
    assert len(session.cards) == 1


def test_create_cards_reports_unexpected_errors(client, session, service):
    session.cards = [make_card('Hallo')]
    service.create_cards.side_effect = RuntimeError('kaboom')

    response = client.post('/create-cards', data={'deck_name': 'Deck'})

    assert 'kaboom' in response.text
    assert len(session.cards) == 1


# --------------------------------------------------------------------------
# POST /delete-card/{index}
# --------------------------------------------------------------------------


def test_delete_card_removes_card_media_and_input_line(
    client, session, service
):
    hallo, tschuss = make_card('Hallo'), make_card('Tschuss')
    session.cards = [hallo, tschuss]
    session.input_text = 'Hallo\nTschuss'

    response = client.post('/delete-card/0')

    assert response.status_code == 200
    assert [c.word for c in session.cards] == ['Tschuss']
    service.cleanup_card_media.assert_awaited_once_with(hallo)
    assert session.input_text == 'Tschuss'
    assert hx_trigger(response)['card-deleted'] == 'Tschuss'


def test_delete_card_returns_one_card_list_not_a_nested_wrapper(
    client, session, service
):
    """The partial already emits <ul id="card-list"> with the grid styles.

    Wrapping it in another #card-list grid nested two grids and duplicated the
    id, which squeezed the real list into a single column - one card per row.
    """
    session.cards = [make_card('eins'), make_card('zwei'), make_card('drei')]

    html = client.post('/delete-card/0').text

    assert html.count('id="card-list"') == 1
    assert "<div id='card-list'" not in html
    # exactly one grid definition, on the <ul> that replaces the real list
    assert html.count('grid-template-columns') == 1
    assert 'hx-swap-oob="true"' in html.split('>')[0]


@pytest.mark.parametrize('index', [-1, 1, 99])
def test_delete_card_ignores_out_of_range_index(client, session, service, index):
    session.cards = [make_card('Hallo')]

    response = client.post(f'/delete-card/{index}')

    assert response.status_code == 200
    assert len(session.cards) == 1
    service.cleanup_card_media.assert_not_awaited()


# --------------------------------------------------------------------------
# POST /clear-cards
# --------------------------------------------------------------------------


def test_clear_cards_wipes_session_and_media(client, session, service):
    session.cards = [make_card('Hallo'), make_card('Tschuss')]
    session.input_text = 'Hallo\nTschuss'

    client.post('/clear-cards')

    assert session.cards == []
    assert session.input_text == ''
    assert service.cleanup_card_media.await_count == 2


# --------------------------------------------------------------------------
# POST /clear-media
# --------------------------------------------------------------------------


def test_clear_media_empties_download_folders(client, service):
    audio = service.config.audio_downloads_folder / 'a.mp3'
    audio.write_bytes(b'a')
    image = service.config.image_downloads_folder / 'i.jpg'
    image.write_bytes(b'i')

    client.post('/clear-media')

    assert not audio.exists()
    assert not image.exists()
    # the folders themselves survive - they are mounted as static routes
    assert service.config.audio_downloads_folder.exists()
    assert service.config.image_downloads_folder.exists()


# --------------------------------------------------------------------------
# POST /update-card/{index}/*
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'photo_source,key_field,message',
    [
        ('pexels', 'pexels_api_key', 'Pexels API Key missing'),
        ('unsplash', 'unsplash_api_key', 'Unsplash API Key missing'),
    ],
)
def test_update_image_requires_a_photo_key(
    client, session, service, photo_source, key_field, message
):
    session.cards = [make_card('Hallo')]
    session.photo_source = photo_source
    setattr(service.config, key_field, '')

    response = client.post('/update-card/0/image')

    assert message in response.text
    service.update_card_image.assert_not_awaited()


def test_update_image_rerolls_and_persists(client, session, service):
    card = make_card('Hallo')
    session.cards = [card]

    async def set_new_image(target):
        target.translation_image_url = '/media/image/new.jpg'

    service.update_card_image.side_effect = set_new_image

    response = client.post('/update-card/0/image')

    assert response.status_code == 200
    assert 'Hallo' in response.text
    assert session.cards[0].translation_image_url == '/media/image/new.jpg'
    assert SessionManager._sessions[session.session_id] is session


def test_update_audio_rerolls_and_persists(client, session, service):
    card = make_card('Hallo')
    session.cards = [card]

    async def set_new_audio(target):
        target.word_audio_url = '/media/audio/new.mp3'

    service.update_card_audio.side_effect = set_new_audio

    response = client.post('/update-card/0/audio')

    assert response.status_code == 200
    assert 'Hallo' in response.text
    assert session.cards[0].word_audio_url == '/media/audio/new.mp3'
    assert SessionManager._sessions[session.session_id] is session


def test_update_image_reports_lookup_failure(client, session, service):
    session.cards = [make_card('Hallo')]
    service.update_card_image.side_effect = RuntimeError('no photos found')

    response = client.post('/update-card/0/image')

    assert 'Image update failed' in response.text
    assert 'no photos found' in response.text


def test_update_audio_reports_failure(client, session, service):
    session.cards = [make_card('Hallo')]
    service.update_card_audio.side_effect = RuntimeError('tts down')

    response = client.post('/update-card/0/audio')

    assert 'Audio update failed' in response.text
    assert 'tts down' in response.text


@pytest.mark.parametrize('endpoint', ['image', 'audio', 'content'])
def test_update_card_ignores_out_of_range_index(client, session, endpoint):
    session.cards = [make_card('Hallo')]

    response = client.post(f'/update-card/5/{endpoint}')

    assert response.status_code == 200
    assert response.text == ''


def test_update_content_keeps_media_and_speaker(client, session, service):
    """Refreshing text must not throw away the audio and image already fetched."""
    session.cards = [
        make_card(
            'Hallo',
            speaker='Hans',
            word_audio_url='/media/audio/hallo.mp3',
            translation_image_url='/media/image/hallo.jpg',
        )
    ]
    refreshed = make_card('Hallo', definition='a better definition')

    with patch('germanki.web.app.LLMAPI') as mock_llm:
        mock_llm.return_value.query_single_card = AsyncMock(return_value=refreshed)
        response = client.post('/update-card/0/content')

    assert response.status_code == 200
    card = session.cards[0]
    assert card.definition == 'a better definition'
    assert card.speaker == 'Hans'
    assert card.word_audio_url == '/media/audio/hallo.mp3'
    assert card.translation_image_url == '/media/image/hallo.jpg'


def test_update_content_requires_an_llm_key(client, session, service):
    session.cards = [make_card('Hallo')]
    service.config.openai_api_key = ''

    response = client.post('/update-card/0/content')

    assert 'LLM API Key missing' in response.text


def test_update_content_reports_llm_failure(client, session, service):
    session.cards = [make_card('Hallo')]
    original = session.cards[0]

    with patch('germanki.web.app.LLMAPI') as mock_llm:
        mock_llm.return_value.query_single_card = AsyncMock(
            side_effect=RuntimeError('rate limited')
        )
        response = client.post('/update-card/0/content')

    assert 'Content refresh failed' in response.text
    assert session.cards[0] is original


# --------------------------------------------------------------------------
# GET /export-cards
# --------------------------------------------------------------------------


def test_export_cards_returns_apkg_attachment(client, session, service):
    session.cards = [make_card('Hallo')]
    session.deck_name = 'My Deck'

    response = client.get('/export-cards')

    assert response.status_code == 200
    assert response.content == b'apkg-bytes'
    assert 'attachment' in response.headers['content-disposition']
    assert response.headers['content-disposition'].endswith('.apkg')
    assert service.export_cards.await_args.kwargs['deck_name'] == 'My Deck'


def test_export_cards_rejects_empty_session(client, session):
    assert session.cards == []

    assert client.get('/export-cards').status_code == 400


def test_export_cards_reports_failure(client, session, service):
    session.cards = [make_card('Hallo')]
    service.export_cards.side_effect = RuntimeError('genanki blew up')

    response = client.get('/export-cards')

    assert response.status_code == 500
    assert 'Export failed' in response.text


# --------------------------------------------------------------------------
# POST /check-duplicates
# --------------------------------------------------------------------------


def test_check_duplicates_lists_words_already_in_anki(client):
    async def find_notes(self, query):
        return [1] if 'Hallo' in query else []

    with patch('germanki.anki_connect.AnkiConnectClient.find_notes', find_notes):
        response = client.post(
            '/check-duplicates',
            data={'input_text': 'Hallo\nTschuss', 'deck_name': 'Deck'},
        )

    assert 'Hallo' in response.text
    assert 'Tschuss' not in response.text


def test_check_duplicates_is_silent_when_nothing_matches(client):
    with patch(
        'germanki.anki_connect.AnkiConnectClient.find_notes',
        AsyncMock(return_value=[]),
    ):
        response = client.post(
            '/check-duplicates', data={'input_text': 'Hallo', 'deck_name': 'Deck'}
        )

    assert response.text == ''


@pytest.mark.parametrize(
    'error',
    [
        pytest.param(AnkiConnectRequestError('refused', None), id='unreachable'),
        pytest.param(
            AnkiConnectResponseError('findNotes', 'invalid search'), id='rejected'
        ),
    ],
)
def test_check_duplicates_is_silent_on_anki_errors(client, error):
    """A duplicate check is advisory - Anki failing must not block the user."""
    with patch(
        'germanki.anki_connect.AnkiConnectClient.find_notes',
        AsyncMock(side_effect=error),
    ):
        response = client.post(
            '/check-duplicates', data={'input_text': 'Hallo', 'deck_name': 'Deck'}
        )

    assert response.status_code == 200
    assert response.text == ''


def test_check_duplicates_does_not_swallow_unrelated_errors(client):
    """Only Anki failures are tolerated; a bug here must not hide as an empty box."""
    with patch(
        'germanki.anki_connect.AnkiConnectClient.find_notes',
        AsyncMock(side_effect=TypeError('bad call signature')),
    ):
        with pytest.raises(TypeError, match='bad call signature'):
            client.post(
                '/check-duplicates',
                data={'input_text': 'Hallo', 'deck_name': 'Deck'},
            )


# --------------------------------------------------------------------------
# POST /settings
# --------------------------------------------------------------------------


def test_settings_updates_only_submitted_fields(client, session):
    session.openai_api_key = 'existing-openai'
    session.selected_speaker = 'Vicki'

    client.post('/settings', data={'speaker': 'Hans'})

    assert session.selected_speaker == 'Hans'
    assert session.openai_api_key == 'existing-openai'


def test_settings_persists_to_session_manager(client, session):
    client.post('/settings', data={'openai_key': 'new-key', 'llm_model': 'gpt-4o'})

    stored = SessionManager._sessions[session.session_id]
    assert stored.openai_api_key == 'new-key'
    assert stored.llm_model == 'gpt-4o'


# --------------------------------------------------------------------------
# POST /restore-session
# --------------------------------------------------------------------------


def test_restore_session_replaces_cards_and_keeps_blank_keys(client, session):
    """The browser restores a snapshot that never carries secrets."""
    session.openai_api_key = 'server-side-key'
    payload = UserSession(
        session_id='ignored',
        cards=[make_card('Hallo')],
        input_text='Hallo',
        deck_name='Restored Deck',
    ).model_dump(mode='json')

    response = client.post('/restore-session', json=payload)

    assert response.json() == {'status': 'restored'}
    assert [c.word for c in session.cards] == ['Hallo']
    assert session.deck_name == 'Restored Deck'
    assert session.openai_api_key == 'server-side-key'


def test_restore_session_accepts_keys_from_payload(client, session):
    payload = UserSession(
        session_id='ignored', openai_api_key='restored-key'
    ).model_dump(mode='json')

    client.post('/restore-session', json=payload)

    assert session.openai_api_key == 'restored-key'


# --------------------------------------------------------------------------
# POST /generate
# --------------------------------------------------------------------------


def test_generate_from_yaml_builds_cards_and_fetches_media(
    client, session, service
):
    yaml_input = (
        '- word: Hallo\n'
        '  translations: [Hello]\n'
        '  definition: a greeting\n'
        '  examples: [Hallo!]\n'
        '  extra: interjection\n'
    )

    response = client.post(
        '/generate', data={'input_text': yaml_input, 'input_source': 'manual'}
    )

    assert response.status_code == 200
    assert [c.word for c in session.cards] == ['Hallo']
    service.populate_media.assert_awaited_once()
    assert service.populate_media.await_args.kwargs['skip_images'] is True


def test_generate_skip_images_follows_the_checkbox(client, session, service):
    yaml_input = (
        '- word: Hallo\n'
        '  translations: [Hello]\n'
        '  definition: a greeting\n'
        '  examples: [Hallo!]\n'
        '  extra: interjection\n'
    )

    client.post(
        '/generate',
        data={
            'input_text': yaml_input,
            'input_source': 'manual',
            'enable_images': 'on',
        },
    )

    assert session.enable_images is True
    assert service.populate_media.await_args.kwargs['skip_images'] is False


def test_generate_reuses_existing_cards_and_only_queries_new_words(
    client, session, service
):
    """Re-submitting the box must not re-pay for cards already generated."""
    session.cards = [make_card('Hallo')]
    new_card = make_card('Tschuss')

    async def fake_query(text, batch_size=10):
        fake_query.asked_for = text
        yield [new_card]

    with patch('germanki.web.app.LLMAPI') as mock_llm:
        mock_llm.return_value.query = fake_query
        response = client.post(
            '/generate',
            data={'input_text': 'Hallo\nTschuss', 'input_source': 'chatgpt'},
        )

    assert response.status_code == 200
    assert fake_query.asked_for == 'Tschuss'
    assert [c.word for c in session.cards] == ['Hallo', 'Tschuss']


def test_generate_asks_the_llm_once_per_repeated_word(
    client, session, service
):
    """A word typed twice must not become two identical cards."""
    asked = []

    async def fake_query(text, batch_size=10):
        asked.append(text)
        yield [make_card(w) for w in text.split('\n')]

    with patch('germanki.web.app.LLMAPI') as mock_llm:
        mock_llm.return_value.query = fake_query
        client.post(
            '/generate',
            data={
                'input_text': 'Hund\nKatze\nhund\n  Hund  \nKatze',
                'input_source': 'chatgpt',
            },
        )

    assert asked == ['Hund\nKatze']
    assert [c.word for c in session.cards] == ['Hund', 'Katze']


def test_generate_drops_cards_removed_from_the_input(client, session, service):
    session.cards = [make_card('Hallo'), make_card('Tschuss')]

    async def fake_query(text, batch_size=10):
        return
        yield  # pragma: no cover - never reached, keeps this an async generator

    with patch('germanki.web.app.LLMAPI') as mock_llm:
        mock_llm.return_value.query = fake_query
        client.post(
            '/generate', data={'input_text': 'Hallo', 'input_source': 'chatgpt'}
        )

    assert [c.word for c in session.cards] == ['Hallo']


def test_generate_reports_missing_llm_key(client, session, service):
    service.config.openai_api_key = ''

    response = client.post(
        '/generate', data={'input_text': 'Hallo', 'input_source': 'chatgpt'}
    )

    assert 'API Key missing' in response.text
    assert session.cards == []


def test_generate_surfaces_errors_in_the_stream(client, session, service):
    """The stream has already returned 200, so errors must arrive as content."""
    response = client.post(
        '/generate', data={'input_text': 'not: [valid', 'input_source': 'manual'}
    )

    assert response.status_code == 200
    assert 'Error:' in response.text


# --------------------------------------------------------------------------
# session cookie handling
# --------------------------------------------------------------------------


def test_root_issues_a_session_cookie_and_renders(service):
    """Smoke test: index.html renders and the visitor gets a session."""
    app.dependency_overrides[get_germanki_service] = lambda: service
    try:
        with patch(
            'germanki.anki_connect.AnkiConnectClient.get_deck_names',
            AsyncMock(return_value=['Default']),
        ):
            response = TestClient(app).get('/')
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'session_id' in response.cookies
    assert SessionManager._sessions


def test_root_renders_without_anki_running(service):
    app.dependency_overrides[get_germanki_service] = lambda: service
    try:
        with patch(
            'germanki.anki_connect.AnkiConnectClient.get_deck_names',
            AsyncMock(side_effect=AnkiConnectRequestError('refused', None)),
        ):
            response = TestClient(app).get('/')
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
