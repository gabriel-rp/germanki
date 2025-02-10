import json
from pathlib import Path
from typing import Optional

import requests
from pydantic.dataclasses import dataclass


@dataclass
class TTSResponse:
    success: bool
    mp3_url: Optional[str] = None
    error_message: Optional[str] = None


class TTSAPI:
    DEFAULT_BASE_URL = 'https://ttsmp3.com'

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url

    def _get_headers(self):
        return {
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

    # TODO: better error handling
    def request_tts(self, msg: str, lang: str) -> TTSResponse:
        url = f'{self.base_url}/makemp3_new.php'
        response = requests.post(
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
                response_data = json.loads(response.content.decode('utf8'))
                mp3_url = response_data.get('MP3')
                if mp3_url:
                    return TTSResponse(success=True, mp3_url=mp3_url)
                return TTSResponse(
                    success=False, error_message='MP3 URL not found.'
                )
            except json.JSONDecodeError:
                return TTSResponse(
                    success=False,
                    error_message='Error decoding JSON response.',
                )
        return TTSResponse(
            success=False,
            error_message=f'Failed with status code {response.status_code}',
        )

    # TODO: better error handling
    def download_mp3(self, mp3_url: str, file_path: Path) -> bool:
        url = f'{self.base_url}/dlmp3.php'
        response = requests.get(
            url,
            headers=self._get_headers(),
            params=dict(
                mp3=mp3_url,
                location='direct',
            ),
            allow_redirects=True,
        )

        if response.status_code == 200:
            with open(file_path, 'wb') as file:
                file.write(response.content)
            return True
        return False
