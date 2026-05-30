import asyncio
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from jinja2 import Environment, FileSystemLoader

from germanki.anki_connect import AnkiMedia, AnkiMediaType
from germanki.config import Config
from germanki.core import (
    AnkiCardCreator,
    AnkiCardInfo,
    Germanki,
    MP3Downloader,
)
from germanki.photos import SearchResponse
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
def germanki_instance():
    config = Config(pexels_api_key='test_key', openai_api_key='test_key')
    return Germanki(photos_client=PexelsClient('test_key'), config=config)


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


def test_convert_query_to_filename():
    filename = Germanki.convert_query_to_filename('Hallo Welt!', ext='jpg')
    assert filename == 'Hallo_Welt.jpg'


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
