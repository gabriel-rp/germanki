import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from germanki.config import Config
from germanki.core import (
    AnkiCardCreator,
    AnkiCardInfo,
    Germanki,
    MediaUpdateException,
    MP3Downloader,
)
from germanki.pexels import PexelsNotFoundError


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
def anki_card_creator():
    return AnkiCardCreator()


@pytest.fixture
def germanki_instance():
    config = Config(pexels_api_key='test_key', openai_api_key='test_key')
    return Germanki(config)


@patch('germanki.tts_mp3.TTSAPI.request_tts')
@patch('germanki.tts_mp3.TTSAPI.download_mp3')
def test_mp3_downloader_success(mock_download, mock_request, tmp_path):
    mock_request.return_value.success = True
    mock_request.return_value.mp3_url = 'https://example.com/audio.mp3'
    mock_download.return_value = True

    file_path = tmp_path / 'test.mp3'
    MP3Downloader.download_mp3('Hallo', 'de', file_path)

    mock_request.assert_called_once_with(msg='Hallo', lang='de')
    mock_download.assert_called_once_with(
        mp3_url='https://example.com/audio.mp3', file_path=file_path
    )


@patch('germanki.tts_mp3.TTSAPI.request_tts')
def test_mp3_downloader_failure(mock_request, tmp_path):
    mock_request.return_value.success = False
    file_path = tmp_path / 'test.mp3'

    with pytest.raises(Exception):
        MP3Downloader.download_mp3('Hallo', 'de', file_path)

    mock_request.assert_called_once_with(msg='Hallo', lang='de')


@patch('germanki.pexels.PexelsClient.search_random_photo')
def test_get_image_success(mock_search, germanki_instance, tmp_path):
    mock_search.return_value.photos = [
        MagicMock(src=MagicMock(large2x='https://example.com/image.jpg'))
    ]

    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b'fake image data'

        image_path = germanki_instance._get_image('Hallo', max_pages=1)
        assert isinstance(image_path, Path)


@patch('germanki.config.Config.image_filepath')
def test_convert_query_to_filename(mock_image_filepath):
    filename = Germanki.convert_query_to_filename('Hallo Welt!', ext='jpg')
    assert filename == 'Hallo_Welt.jpg'
