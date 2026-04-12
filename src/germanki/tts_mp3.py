import json
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel


class TTSResponse(BaseModel):
    success: bool
    mp3_url: str | None = None
    error_message: str | None = None


class TTSAPI:
    DEFAULT_BASE_URL: Final[str] = 'https://ttsmp3.com'

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url

    def _get_headers(self):
        return {
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

    async def request_tts(self, msg: str, lang: str) -> TTSResponse:
        url = f'{self.base_url}/makemp3_new.php'
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                data=dict(
                    msg=msg,
                    lang=lang,
                    source='ttsmp3',
                ),
            )

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    mp3_url = response_data.get('MP3')
                    if mp3_url:
                        return TTSResponse(success=True, mp3_url=mp3_url)
                    return TTSResponse(
                        success=False, error_message='MP3 URL not found.'
                    )
                except (json.JSONDecodeError, ValueError):
                    return TTSResponse(
                        success=False,
                        error_message='Error decoding JSON response.',
                    )
            return TTSResponse(
                success=False,
                error_message=f'Failed with status code {response.status_code}',
            )

    async def download_mp3(self, mp3_url: str, file_path: Path) -> bool:
        url = f'{self.base_url}/dlmp3.php'
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                params=dict(
                    mp3=mp3_url,
                    location='direct',
                ),
                follow_redirects=True,
            )

            if response.status_code == 200:
                file_path.write_bytes(response.content)
                return True
            return False
