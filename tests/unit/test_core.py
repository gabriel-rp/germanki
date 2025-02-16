import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from germanki.anki_connect import AnkiMedia, AnkiMediaType
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


def test_anki_card_creator_front(test_card_info):
    audio_with_autoplay = AnkiCardCreator.front(
        test_card_info,
        audio=AnkiMedia(path='test', anki_media_type=AnkiMediaType.AUDIO),
        path='my/path/to/audio.mp3',
        autoplay=True,
    )
    assert audio_with_autoplay.replace(' ', '') == (
        'Hallo<br>'
        '<audio controls autoplay src="my/path/to/audio.mp3"'
        'style=""></audio>'
    ).replace(' ', '')

    audio_with_autoplay_and_style = AnkiCardCreator.front(
        test_card_info,
        audio=AnkiMedia(path='test', anki_media_type=AnkiMediaType.AUDIO),
        path='my/path/to/audio.mp3',
        autoplay=True,
        style='width: 100%;',
    )
    assert audio_with_autoplay_and_style.replace(' ', '') == (
        'Hallo<br>'
        '<audio controls autoplay src="my/path/to/audio.mp3"'
        'style="width: 100%;"></audio>'
    ).replace(' ', '')

    audio_without_autoplay = AnkiCardCreator.front(
        test_card_info,
        audio=AnkiMedia(path='test', anki_media_type=AnkiMediaType.AUDIO),
        path='my/path/to/audio.mp3',
        autoplay=False,
    )
    assert audio_without_autoplay.replace(' ', '') == (
        'Hallo<br>'
        '<audio controls src="my/path/to/audio.mp3"'
        'style=""></audio>'
    ).replace(' ', '')


def test_anki_card_creator_back(test_card_info):
    image_without_style = AnkiCardCreator.back(
        test_card_info,
        image=AnkiMedia(path='test', anki_media_type=AnkiMediaType.IMAGE),
        path='my/path/to/image.jpg',
        style='',
    )
    assert image_without_style.replace(' ', '') == (
        'Hello<br><img src="my/path/to/image.jpg" style="">'
    ).replace(' ', '')

    image_with_style = AnkiCardCreator.back(
        test_card_info,
        image=AnkiMedia(path='test', anki_media_type=AnkiMediaType.IMAGE),
        path='my/path/to/image.jpg',
        style='width: 100%;',
    )
    assert image_with_style.replace(' ', '') == (
        'Hello<br><img src="my/path/to/image.jpg" style="width: 100%;">'
    ).replace(' ', '')


def test_anki_card_creator_extra(test_card_info):
    assert AnkiCardCreator.extra(test_card_info,).replace(' ', '') == (
        'Common German greeting<br><br>'
        'Erklärung: A greeting in German<br><br>'
        "Beispiele:<br>1. Hallo,wiegeht's?"
    ).replace(' ', '')


@patch('pathlib.Path.relative_to', new=lambda self, _: self.stem)
def test_anki_card_creator_html_preview():
    anki_card_info = AnkiCardInfo(
        word='Hallo',
        translations=['Hello'],
        definition='A greeting in German',
        examples=["Hallo, wie geht's?"],
        extra='Common German greeting',
        word_audio_url='my/path/to/audio.mp3',
        translation_image_url='my/path/to/image.jpg',
    )
    preview = AnkiCardCreator.html_preview(anki_card_info)

    assert preview.front.replace(' ', '') == (
        'Hallo<br>'
        '<audio controls src="http://localhost:8501/app/audio"'
        'style="width:100%;"></audio>'
    ).replace(' ', '')

    assert preview.back.replace(' ', '') == (
        'Hello<br><img src="http://localhost:8501/app/image" style="">'
    ).replace(' ', '')

    assert preview.extra.replace(' ', '') == (
        'Common German greeting<br><br>'
        'Erklärung: A greeting in German<br><br>'
        "Beispiele:<br>1. Hallo,wiegeht's?"
    ).replace(' ', '')
