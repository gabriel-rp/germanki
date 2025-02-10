import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from germanki.tts_mp3 import TTSAPI, TTSResponse


@pytest.fixture()
def tts_client():
    return TTSAPI()


@patch('requests.post')
def test_request_tts_success(mock_post, tts_client: TTSAPI):
    mock_post.return_value.status_code = 200
    mock_post.return_value.content = json.dumps(
        {'MP3': 'https://example.com/audio.mp3'}
    ).encode('utf8')
    response = tts_client.request_tts('Hello world', 'en')
    assert response.success is True
    assert response.mp3_url == 'https://example.com/audio.mp3'
    assert response.error_message is None


@patch('requests.post')
def test_request_tts_no_mp3_url(mock_post, tts_client: TTSAPI):
    mock_post.return_value.status_code = 200
    mock_post.return_value.content = json.dumps({}).encode('utf8')
    response = tts_client.request_tts('Hello world', 'en')
    assert response.success is False
    assert response.mp3_url is None
    assert response.error_message == 'MP3 URL not found.'


@patch('requests.post')
def test_request_tts_invalid_json(mock_post, tts_client: TTSAPI):
    mock_post.return_value.status_code = 200
    mock_post.return_value.content = b'invalid json'
    response = tts_client.request_tts('Hallo', 'de')
    assert response.success is False
    assert response.mp3_url is None
    assert response.error_message == 'Error decoding JSON response.'


@patch('requests.post')
def test_request_tts_http_error(mock_post, tts_client: TTSAPI):
    mock_post.return_value.status_code = 500
    response = tts_client.request_tts('Hallo', 'de')
    assert response.success is False
    assert response.mp3_url is None
    assert response.error_message == 'Failed with status code 500'


@patch('requests.get')
def test_download_mp3_success(mock_get, tts_client: TTSAPI, tmp_path: Path):
    mock_get.return_value.status_code = 200
    mock_get.return_value.content = b'mp3 data'
    file_path = tmp_path / 'test.mp3'
    result = tts_client.download_mp3(
        'https://example.com/audio.mp3', file_path
    )
    assert result is True
    assert file_path.exists()
    assert file_path.read_bytes() == b'mp3 data'


@patch('requests.get')
def test_download_mp3_http_error(mock_get, tts_client: TTSAPI, tmp_path: Path):
    mock_get.return_value.status_code = 404
    file_path = tmp_path / 'test.mp3'
    result = tts_client.download_mp3(
        'https://example.com/audio.mp3', file_path
    )
    assert result is False
    assert not file_path.exists()
