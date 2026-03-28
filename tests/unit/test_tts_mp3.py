from pathlib import Path
import pytest
import respx
import httpx
from germanki.tts_mp3 import TTSAPI, TTSResponse


@pytest.fixture
def tts_api():
    return TTSAPI()


@pytest.mark.asyncio
@respx.mock
async def test_request_tts_success(tts_api):
    respx.post("https://ttsmp3.com/makemp3_new.php").mock(return_value=httpx.Response(200, json={'MP3': 'test.mp3'}))
    response = await tts_api.request_tts('Hallo', 'de')
    assert response.success is True
    assert response.mp3_url == 'test.mp3'


@pytest.mark.asyncio
@respx.mock
async def test_request_tts_failure(tts_api):
    respx.post("https://ttsmp3.com/makemp3_new.php").mock(return_value=httpx.Response(500))
    response = await tts_api.request_tts('Hallo', 'de')
    assert response.success is False
    assert 'Failed' in response.error_message


@pytest.mark.asyncio
@respx.mock
async def test_download_mp3_success(tts_api, tmp_path):
    respx.get("https://ttsmp3.com/dlmp3.php").mock(return_value=httpx.Response(200, content=b'mp3_data'))
    file_path = tmp_path / 'test.mp3'
    success = await tts_api.download_mp3('test.mp3', file_path)
    assert success is True
    assert file_path.read_bytes() == b'mp3_data'


@pytest.mark.asyncio
@respx.mock
async def test_download_mp3_failure(tts_api, tmp_path):
    respx.get("https://ttsmp3.com/dlmp3.php").mock(return_value=httpx.Response(404))
    file_path = tmp_path / 'test.mp3'
    success = await tts_api.download_mp3('test.mp3', file_path)
    assert success is False
