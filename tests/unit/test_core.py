import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from jinja2 import Environment, FileSystemLoader

from germanki.anki_connect import (
    AnkiConnectClient,
    AnkiConnectResponseError,
    AnkiMedia,
    AnkiMediaType,
)
from germanki.config import Config
from germanki.core import (
    AnkiCardCreator,
    AnkiCardInfo,
    Germanki,
    ImageUpdateException,
    MediaUpdateException,
    MP3Downloader,
)
from germanki.photos import SearchResponse
from germanki.photos.exceptions import PhotosNotFoundError
from germanki.photos.pexels import PexelsClient


@pytest.fixture
def test_card_info():
    return AnkiCardInfo(
        word='Hallo',
        translations=['Hello'],
        definition='A greeting in German',
        examples=["Hallo, wie geht's?"],
        extra='Common German greeting',
        speaker='Vicki',
    )


@pytest.fixture
def jinja_env():
    templates_dir = (
        Path(__file__).parent.parent.parent
        / 'src'
        / 'germanki'
        / 'web'
        / 'templates'
    )
    return Environment(loader=FileSystemLoader(str(templates_dir)))


@pytest.fixture
def config(tmp_path):
    """Config isolated to tmp_path so tests never touch the real user data dir."""
    return Config(
        pexels_api_key='test_key',
        openai_api_key='test_key',
        audio_downloads_folder=tmp_path / 'audio',
        image_downloads_folder=tmp_path / 'image',
    )


@pytest.fixture
def germanki_instance(config):
    return Germanki(photos_client=PexelsClient('test_key'), config=config)


@pytest.fixture
def anki_client():
    """AnkiConnectClient double with every awaited method stubbed."""
    client = MagicMock(spec=AnkiConnectClient)
    for name in (
        'add_card',
        'create_model',
        'get_model_info',
        'get_model_names',
        'update_model_styling',
        'update_model_templates',
    ):
        setattr(client, name, AsyncMock())
    return client


@pytest.mark.asyncio
@patch('germanki.tts_mp3.TTSAPI.request_tts')
@patch('germanki.tts_mp3.TTSAPI.download_mp3')
async def test_mp3_downloader_success(mock_download, mock_request, tmp_path):
    mock_request.return_value.success = True
    mock_request.return_value.mp3_url = 'https://example.com/audio.mp3'
    mock_download.return_value = True

    file_path = tmp_path / 'test.mp3'
    await MP3Downloader.download_mp3('Hallo', 'de', file_path)

    mock_request.assert_called_once_with(msg='Hallo', lang='de')
    mock_download.assert_called_once_with(
        mp3_url='https://example.com/audio.mp3', file_path=file_path
    )


@pytest.mark.asyncio
@patch('germanki.tts_mp3.TTSAPI.request_tts')
async def test_mp3_downloader_failure(mock_request, tmp_path):
    mock_request.return_value.success = False
    mock_request.return_value.error_message = 'Error'
    file_path = tmp_path / 'test.mp3'

    with pytest.raises(Exception):
        await MP3Downloader.download_mp3('Hallo', 'de', file_path)


@pytest.mark.asyncio
@respx.mock
async def test_get_image_success(germanki_instance):
    with patch.object(PexelsClient, 'search_random_photo') as mock_search:
        mock_search.return_value = SearchResponse(
            photo_urls=['https://example.com/image.jpg'], total_results=1
        )
        respx.get('https://example.com/image.jpg').mock(
            return_value=httpx.Response(200, content=b'fake image data')
        )

        image_path = await germanki_instance._get_image('Hallo', max_pages=1)
        assert isinstance(image_path, Path)


@patch('pathlib.Path.read_bytes', new=lambda _: b'b64_audio')
def test_anki_card_creator_front(test_card_info, jinja_env):
    front_html = AnkiCardCreator.front(
        jinja_env,
        test_card_info,
        audio=AnkiMedia(
            path=Path('test'), anki_media_type=AnkiMediaType.AUDIO
        ),
    )
    assert 'Hallo' in front_html
    # base64.b64encode(b'b64_audio').decode() is 'YjY0X2F1ZGlv'
    assert 'data:audio/mp3;base64,YjY0X2F1ZGlv' in front_html


def test_anki_card_creator_back(test_card_info, jinja_env):
    back_html = AnkiCardCreator.back(
        jinja_env,
        test_card_info,
        image=AnkiMedia(
            path=Path('test.jpg'), anki_media_type=AnkiMediaType.IMAGE
        ),
        style='width: 100%;',
    )
    assert 'Hello' in back_html
    assert '<img src="test.jpg" style="width: 100%;">' in back_html


def test_anki_card_creator_extra(test_card_info, jinja_env):
    extra_html = AnkiCardCreator.extra(jinja_env, test_card_info)
    assert 'Common German greeting' in extra_html
    assert 'Erklärung: A greeting in German' in extra_html
    assert "1. Hallo, wie geht's?" in extra_html


@pytest.mark.asyncio
async def test_export_cards(germanki_instance, test_card_info, jinja_env, tmp_path):
    import zipfile
    import io

    # Mock media files
    audio_path = tmp_path / "test.mp3"
    audio_path.write_bytes(b"fake audio")
    test_card_info.word_audio_url = str(audio_path)

    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake image")
    test_card_info.translation_image_url = str(image_path)

    apkg_bytes = await germanki_instance.export_cards(jinja_env, [test_card_info], deck_name="My Test Deck")
    
    assert len(apkg_bytes) > 0
    
    with zipfile.ZipFile(io.BytesIO(apkg_bytes)) as z:
        # An apkg is a zip containing collection.anki21 (or .anki2) and media
        filenames = z.namelist()
        assert any(f.startswith("collection.anki2") for f in filenames)
        assert "media" in filenames


async def up_to_date_model_info(germanki):
    """The model info AnkiConnect reports for a freshly created germanki_card.

    Derived from `_ensure_germanki_model` instead of copied from it, so editing
    a card template in core.py doesn't break every check_model_outdated test.
    """
    client = MagicMock(spec=AnkiConnectClient)
    client.get_model_names = AsyncMock(return_value=[])
    client.create_model = AsyncMock()

    await germanki._ensure_germanki_model(client)

    kwargs = client.create_model.await_args.kwargs
    return {
        'css': kwargs['css'],
        'tmpls': [
            {'name': t['Name'], 'qfmt': t['Front'], 'afmt': t['Back']}
            for t in kwargs['card_templates']
        ],
    }


# --------------------------------------------------------------------------
# AnkiCardInfo
# --------------------------------------------------------------------------


def test_query_words_prefers_image_query_words_over_translations(test_card_info):
    assert test_card_info.query_words == ['Hello']

    test_card_info.image_query_words = ['greeting', 'wave']
    assert test_card_info.query_words == ['greeting', 'wave']


# --------------------------------------------------------------------------
# AnkiCardCreator.create
# --------------------------------------------------------------------------


def test_create_builds_card_with_both_media(test_card_info, jinja_env, tmp_path):
    audio_path = tmp_path / 'hallo.mp3'
    audio_path.write_bytes(b'audio')
    image_path = tmp_path / 'hello.jpg'
    image_path.write_bytes(b'image')
    test_card_info.word_audio_url = str(audio_path)
    test_card_info.translation_image_url = str(image_path)

    card = AnkiCardCreator.create(jinja_env, test_card_info)

    assert 'Hallo' in card.front
    assert base64.b64encode(b'audio').decode() in card.front
    assert 'hello.jpg' in card.back
    assert 'Common German greeting' in card.extra
    assert [m.filename for m in card.media] == ['hello.jpg', 'hallo.mp3']


def test_create_builds_card_without_media(test_card_info, jinja_env):
    card = AnkiCardCreator.create(jinja_env, test_card_info)

    assert card.media == []
    assert '<audio' not in card.front
    assert '<img' not in card.back


# --------------------------------------------------------------------------
# MP3Downloader
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@patch('germanki.tts_mp3.TTSAPI.request_tts')
@patch('germanki.tts_mp3.TTSAPI.download_mp3')
async def test_mp3_downloader_raises_when_download_fails(
    mock_download, mock_request, tmp_path
):
    mock_request.return_value.success = True
    mock_request.return_value.mp3_url = 'https://example.com/audio.mp3'
    mock_download.return_value = False

    with pytest.raises(Exception, match='Failed to download MP3'):
        await MP3Downloader.download_mp3('Hallo', 'de', tmp_path / 'test.mp3')


# --------------------------------------------------------------------------
# speaker selection
# --------------------------------------------------------------------------


def test_selected_speaker_rejects_unknown_speaker(germanki_instance):
    with pytest.raises(ValueError, match='Invalid speaker.'):
        germanki_instance.selected_speaker = 'Nobody'


# --------------------------------------------------------------------------
# update_card_image
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_card_image_sets_url(
    germanki_instance, test_card_info, tmp_path
):
    new_image = tmp_path / 'new.jpg'
    with patch.object(
        germanki_instance, '_get_image', AsyncMock(return_value=new_image)
    ) as mock_get:
        await germanki_instance.update_card_image(test_card_info)

    mock_get.assert_awaited_once_with('Hello')
    assert test_card_info.translation_image_url == str(new_image)


@pytest.mark.asyncio
async def test_update_card_image_deletes_replaced_file(
    germanki_instance, test_card_info, tmp_path
):
    """Re-rolling an image must not leak the old file onto disk."""
    old_image = tmp_path / 'old.jpg'
    old_image.write_bytes(b'old')
    test_card_info.translation_image_url = str(old_image)
    new_image = tmp_path / 'new.jpg'

    with patch.object(
        germanki_instance, '_get_image', AsyncMock(return_value=new_image)
    ):
        await germanki_instance.update_card_image(test_card_info)

    assert not old_image.exists()
    assert test_card_info.translation_image_url == str(new_image)


@pytest.mark.asyncio
async def test_update_card_image_falls_back_to_next_query_word(
    germanki_instance, test_card_info, tmp_path
):
    test_card_info.image_query_words = ['obscure', 'common']
    new_image = tmp_path / 'common.jpg'

    with patch.object(
        germanki_instance,
        '_get_image',
        AsyncMock(side_effect=[PhotosNotFoundError('nope'), new_image]),
    ) as mock_get:
        await germanki_instance.update_card_image(test_card_info)

    assert mock_get.await_count == 2
    assert test_card_info.translation_image_url == str(new_image)


@pytest.mark.asyncio
async def test_update_card_image_raises_when_every_query_fails(
    germanki_instance, test_card_info
):
    test_card_info.image_query_words = ['a', 'b', 'c']

    with patch.object(
        germanki_instance,
        '_get_image',
        AsyncMock(side_effect=PhotosNotFoundError('nope')),
    ) as mock_get:
        with pytest.raises(ImageUpdateException) as excinfo:
            await germanki_instance.update_card_image(test_card_info)

    assert mock_get.await_count == 3
    assert excinfo.value.query_words == ['a', 'b', 'c']
    assert test_card_info.translation_image_url is None


# --------------------------------------------------------------------------
# update_card_audio
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_card_audio_sets_url_and_deletes_replaced_file(
    germanki_instance, test_card_info, tmp_path
):
    old_audio = tmp_path / 'old.mp3'
    old_audio.write_bytes(b'old')
    test_card_info.word_audio_url = str(old_audio)
    new_audio = tmp_path / 'new.mp3'

    with patch.object(
        germanki_instance, '_get_tts_audio', AsyncMock(return_value=new_audio)
    ) as mock_get:
        await germanki_instance.update_card_audio(test_card_info)

    mock_get.assert_awaited_once_with('Hallo')
    assert test_card_info.word_audio_url == str(new_audio)
    assert not old_audio.exists()


@pytest.mark.asyncio
async def test_update_card_audio_wraps_failure(germanki_instance, test_card_info):
    cause = RuntimeError('tts down')
    with patch.object(
        germanki_instance, '_get_tts_audio', AsyncMock(side_effect=cause)
    ):
        with pytest.raises(MediaUpdateException) as excinfo:
            await germanki_instance.update_card_audio(test_card_info)

    assert excinfo.value.query == 'Hallo'
    assert excinfo.value.media_type == 'audio'
    assert excinfo.value.exception is cause


# --------------------------------------------------------------------------
# populate_media
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('skip_images', [False, True])
async def test_populate_media_updates_each_card(
    germanki_instance, test_card_info, skip_images
):
    with (
        patch.object(
            germanki_instance, 'update_card_image', AsyncMock()
        ) as mock_image,
        patch.object(
            germanki_instance, 'update_card_audio', AsyncMock()
        ) as mock_audio,
    ):
        exceptions = await germanki_instance.populate_media(
            [test_card_info], skip_images=skip_images
        )

    assert exceptions == []
    assert mock_image.await_count == (0 if skip_images else 1)
    mock_audio.assert_awaited_once_with(test_card_info)


@pytest.mark.asyncio
async def test_populate_media_returns_failures_instead_of_raising(
    germanki_instance, test_card_info
):
    """One dead image lookup must not abort the whole batch."""
    image_error = ImageUpdateException(query_words=['Hello'], exceptions=[])
    audio_error = MediaUpdateException(
        query='Hallo', media_type='audio', exception=ValueError()
    )

    with (
        patch.object(
            germanki_instance, 'update_card_image', AsyncMock(side_effect=image_error)
        ),
        patch.object(
            germanki_instance, 'update_card_audio', AsyncMock(side_effect=audio_error)
        ),
    ):
        exceptions = await germanki_instance.populate_media([test_card_info])

    assert exceptions == [image_error, audio_error]


# --------------------------------------------------------------------------
# cleanup_card_media
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_card_media_deletes_both_files(
    germanki_instance, test_card_info, tmp_path
):
    audio_path = tmp_path / 'a.mp3'
    audio_path.write_bytes(b'a')
    image_path = tmp_path / 'i.jpg'
    image_path.write_bytes(b'i')
    test_card_info.word_audio_url = str(audio_path)
    test_card_info.translation_image_url = str(image_path)

    await germanki_instance.cleanup_card_media(test_card_info)

    assert not audio_path.exists()
    assert not image_path.exists()


# --------------------------------------------------------------------------
# create_cards
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cards_success_cleans_up_media(
    germanki_instance, test_card_info, jinja_env, anki_client, tmp_path
):
    audio_path = tmp_path / 'a.mp3'
    audio_path.write_bytes(b'a')
    test_card_info.word_audio_url = str(audio_path)
    anki_client.get_model_names.return_value = ['germanki_card']

    with patch('germanki.core.AnkiConnectClient', return_value=anki_client):
        responses = await germanki_instance.create_cards(
            jinja_env, [test_card_info], deck_name='Deck'
        )

    assert len(responses) == 1
    assert responses[0].card_word == 'Hallo'
    assert responses[0].exception is None
    assert anki_client.add_card.await_args.kwargs['deck_name'] == 'Deck'
    assert anki_client.add_card.await_args.kwargs['model'] == 'germanki_card'
    # media is removed once Anki has its own copy
    assert not audio_path.exists()


@pytest.mark.asyncio
async def test_create_cards_records_anki_errors_and_keeps_media(
    germanki_instance, test_card_info, jinja_env, anki_client, tmp_path
):
    """A rejected card keeps its media so it can be retried."""
    audio_path = tmp_path / 'a.mp3'
    audio_path.write_bytes(b'a')
    test_card_info.word_audio_url = str(audio_path)
    anki_client.get_model_names.return_value = ['germanki_card']
    anki_client.add_card.side_effect = AnkiConnectResponseError(
        'addNote', 'cannot create note because it is a duplicate'
    )

    with patch('germanki.core.AnkiConnectClient', return_value=anki_client):
        responses = await germanki_instance.create_cards(
            jinja_env, [test_card_info], deck_name='Deck'
        )

    assert isinstance(responses[0].exception, AnkiConnectResponseError)
    assert 'duplicate' in str(responses[0].exception)
    assert audio_path.exists()


@pytest.mark.asyncio
async def test_create_cards_continues_when_model_setup_fails(
    germanki_instance, test_card_info, jinja_env, anki_client
):
    """A failed model check must not abort card creation."""
    anki_client.get_model_names.side_effect = RuntimeError('anki offline')

    with patch('germanki.core.AnkiConnectClient', return_value=anki_client):
        responses = await germanki_instance.create_cards(
            jinja_env, [test_card_info], deck_name='Deck'
        )

    assert len(responses) == 1
    anki_client.add_card.assert_awaited_once()


# --------------------------------------------------------------------------
# _ensure_germanki_model
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_model_creates_when_absent(germanki_instance, anki_client):
    anki_client.get_model_names.return_value = ['Basic']

    await germanki_instance._ensure_germanki_model(anki_client)

    kwargs = anki_client.create_model.await_args.kwargs
    assert kwargs['model_name'] == 'germanki_card'
    # field names are a contract with AnkiCardCreator and export_cards
    assert kwargs['in_order_fields'] == ['Front', 'Back', 'Extra']
    assert len(kwargs['card_templates']) == 2
    anki_client.update_model_templates.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_model_leaves_existing_model_alone(
    germanki_instance, anki_client
):
    """Without force_update, never clobber a model the user may have edited."""
    anki_client.get_model_names.return_value = ['germanki_card']

    await germanki_instance._ensure_germanki_model(anki_client)

    anki_client.create_model.assert_not_awaited()
    anki_client.update_model_templates.assert_not_awaited()
    anki_client.update_model_styling.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_model_force_update_rewrites_templates_and_css(
    germanki_instance, anki_client
):
    anki_client.get_model_names.return_value = ['germanki_card']

    await germanki_instance._ensure_germanki_model(anki_client, force_update=True)

    anki_client.create_model.assert_not_awaited()
    model_name, templates = anki_client.update_model_templates.await_args.args
    assert model_name == 'germanki_card'
    assert len(templates) == 2
    assert all(set(t) == {'Front', 'Back'} for t in templates.values())
    anki_client.update_model_styling.assert_awaited_once()
    assert anki_client.update_model_styling.await_args.args[0] == 'germanki_card'


# --------------------------------------------------------------------------
# check_model_outdated
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_model_outdated_false_when_model_absent(
    germanki_instance, anki_client
):
    anki_client.get_model_names.return_value = ['Basic']

    assert await germanki_instance.check_model_outdated(anki_client) is False
    anki_client.get_model_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_model_outdated_false_when_model_matches(
    germanki_instance, anki_client
):
    anki_client.get_model_names.return_value = ['germanki_card']
    anki_client.get_model_info.return_value = await up_to_date_model_info(
        germanki_instance
    )

    assert await germanki_instance.check_model_outdated(anki_client) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mutate',
    [
        pytest.param(
            lambda i: i.update(css='.card { color: red; }'), id='css-edited'
        ),
        pytest.param(
            lambda i: i.update(tmpls=i['tmpls'][:1]), id='template-removed'
        ),
        pytest.param(
            lambda i: i['tmpls'][0].update(name='Card 1'), id='template-renamed'
        ),
        pytest.param(
            lambda i: i['tmpls'][0].update(qfmt='{{Word}}'), id='question-edited'
        ),
        pytest.param(
            lambda i: i['tmpls'][1].update(afmt='{{FrontSide}}'), id='answer-edited'
        ),
    ],
)
async def test_check_model_outdated_detects_drift(
    germanki_instance, anki_client, mutate
):
    info = await up_to_date_model_info(germanki_instance)
    mutate(info)
    anki_client.get_model_names.return_value = ['germanki_card']
    anki_client.get_model_info.return_value = info

    assert await germanki_instance.check_model_outdated(anki_client) is True


# --------------------------------------------------------------------------
# _get_image
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_image_reuses_cached_file(germanki_instance, config):
    """A cache hit must not spend a Pexels API call."""
    cached = config.image_filepath('Hallo_1.jpg')
    cached.write_bytes(b'cached')

    with (
        patch('germanki.core.randint', return_value=1),
        patch.object(PexelsClient, 'search_random_photo') as mock_search,
    ):
        result = await germanki_instance._get_image('Hallo', max_pages=1)

    assert result == cached
    mock_search.assert_not_called()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    'response',
    [
        pytest.param(httpx.Response(404), id='not-found'),
        pytest.param(httpx.Response(200, content=b''), id='empty-body'),
    ],
)
async def test_get_image_raises_on_bad_download(germanki_instance, response):
    with (
        patch('germanki.core.randint', return_value=1),
        patch.object(
            PexelsClient,
            'search_random_photo',
            AsyncMock(
                return_value=SearchResponse(
                    photo_urls=['https://example.com/image.jpg'], total_results=1
                )
            ),
        ),
    ):
        respx.get('https://example.com/image.jpg').mock(return_value=response)

        with pytest.raises(Exception, match='Error downloading image'):
            await germanki_instance._get_image('Hallo', max_pages=1)


@pytest.mark.asyncio
@respx.mock
async def test_get_image_retries_lower_page_range_on_no_results(germanki_instance):
    """An empty high page walks back into a lower page range and retries."""
    with (
        patch('germanki.core.randint', side_effect=[10, 3]),
        patch.object(
            PexelsClient,
            'search_random_photo',
            AsyncMock(
                side_effect=[
                    SearchResponse(photo_urls=[], total_results=0),
                    SearchResponse(
                        photo_urls=['https://example.com/image.jpg'],
                        total_results=1,
                    ),
                ]
            ),
        ) as mock_search,
    ):
        respx.get('https://example.com/image.jpg').mock(
            return_value=httpx.Response(200, content=b'image bytes')
        )

        result = await germanki_instance._get_image('Hallo', max_pages=20)

    assert mock_search.await_count == 2
    assert result.read_bytes() == b'image bytes'


@pytest.mark.asyncio
async def test_get_image_gives_up_when_no_page_has_results(germanki_instance):
    """Exhausting the page range reports "no images", not a randint crash."""
    with (
        patch('germanki.core.randint', side_effect=[8, 3, 1]),
        patch.object(
            PexelsClient,
            'search_random_photo',
            AsyncMock(
                return_value=SearchResponse(photo_urls=[], total_results=0)
            ),
        ) as mock_search,
    ):
        with pytest.raises(PhotosNotFoundError):
            await germanki_instance._get_image('Hallo', max_pages=16)

    # 8 -> max_pages 4, 3 -> max_pages 1, then page 1 gives up
    assert mock_search.await_count == 3


@pytest.mark.asyncio
async def test_get_image_gives_up_immediately_when_page_one_is_empty(
    germanki_instance,
):
    with (
        patch('germanki.core.randint', return_value=1),
        patch.object(
            PexelsClient,
            'search_random_photo',
            AsyncMock(
                return_value=SearchResponse(photo_urls=[], total_results=0)
            ),
        ) as mock_search,
    ):
        with pytest.raises(PhotosNotFoundError):
            await germanki_instance._get_image('Hallo', max_pages=1)

    assert mock_search.await_count == 1


# --------------------------------------------------------------------------
# _get_tts_audio
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tts_audio_reuses_cached_file(germanki_instance, config):
    cached = config.audio_filepath('Hallo_Vicki.mp3')
    cached.write_bytes(b'cached')

    with patch('germanki.core.MP3Downloader.download_mp3') as mock_download:
        result = await germanki_instance._get_tts_audio('Hallo')

    assert result == cached
    mock_download.assert_not_called()


@pytest.mark.asyncio
async def test_get_tts_audio_downloads_and_caches_per_speaker(
    germanki_instance, config
):
    germanki_instance.selected_speaker = 'Hans'

    async def fake_download(msg, lang, file_path):
        Path(file_path).write_bytes(b'mp3 bytes')

    with patch(
        'germanki.core.MP3Downloader.download_mp3', side_effect=fake_download
    ) as mock_download:
        result = await germanki_instance._get_tts_audio('Hallo')

    assert mock_download.await_args.kwargs['msg'] == 'Hallo'
    assert mock_download.await_args.kwargs['lang'] == 'Hans'
    # speaker is part of the cache key, so switching voices re-downloads
    assert result == config.audio_filepath('Hallo_Hans.mp3')
    assert result.read_bytes() == b'mp3 bytes'


# --------------------------------------------------------------------------
# convert_query_to_filename
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'query,expected',
    [
        ('Hallo Welt!', 'Hallo_Welt.jpg'),
        ('  Hallo  ', 'Hallo.jpg'),
        ('was?!/\\*', 'was.jpg'),
        ('keep-me_1', 'keep-me_1.jpg'),
        ('a' * 200, 'a' * 50 + '.jpg'),
    ],
)
def test_convert_query_to_filename(query, expected):
    assert Germanki.convert_query_to_filename(query, ext='jpg') == expected
