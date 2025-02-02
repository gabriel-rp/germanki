from functools import cache
from typing import Optional

import requests
from pydantic.dataclasses import dataclass


@dataclass
class ImageResponse:
    success: bool
    image_url: Optional[str] = None
    error_message: Optional[str] = None


class PexelsAPI:
    DEFAULT_BASE_URL = 'https://api.pexels.com'

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url

    def _get_headers(self):
        return {'Authorization': self.api_key}

    @cache
    def search_images(
        self,
        query: str,
        per_page: int,
        page: int,
        orientation: str,
    ) -> ImageResponse:
        response = requests.get(
            f'{self.base_url}/v1/search',
            headers=self._get_headers(),
            params=dict(
                query=query,
                per_page=per_page,
                page=page,
                orientation=orientation,
            ),
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('photos'):
                image_url = data['photos'][0]['src']['original']
                return ImageResponse(success=True, image_url=image_url)
            return ImageResponse(
                success=False, error_message='No photos found.'
            )
        return ImageResponse(
            success=False,
            error_message=f'Failed with status code {response.status_code}',
        )
