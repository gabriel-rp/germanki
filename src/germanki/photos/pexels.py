import os
from typing import Any, Final

import httpx
from pydantic import BaseModel

from germanki.photos import PhotosClient, SearchResponse
from germanki.photos.exceptions import (
    PhotosAPIError,
    PhotosAuthenticationError,
    PhotosNoResultsError,
    PhotosNotFoundError,
    PhotosRateLimitError,
)
from germanki.utils import get_logger

logger = get_logger(__file__)


class PexelsPhotoSource(BaseModel):
    large2x: str


class PexelsPhotoInfo(BaseModel):
    src: PexelsPhotoSource


class PexelsSearchResponse(BaseModel):
    photos: list[PexelsPhotoInfo]
    total_results: int

    def get_search_response(self) -> SearchResponse:
        return SearchResponse(
            photo_urls=[photo.src.large2x for photo in self.photos],
            total_results=self.total_results,
        )


class PexelsClient(PhotosClient):
    BASE_URL: Final[str] = 'https://api.pexels.com/v1/'

    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.getenv('PEXELS_API_KEY')
        super().__init__(api_key=api_key)

    @property
    def headers(self):
        if not self.api_key:
            raise PhotosAuthenticationError('Pexels API key is missing.')
        return {'Authorization': self.api_key}

    async def _request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handles API requests asynchronously."""
        url = f'{self.BASE_URL}{endpoint}'
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers=self.headers, params=params
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                raise PhotosAuthenticationError(
                    'Invalid API key or unauthorized access.'
                )
            elif response.status_code == 403:
                raise PhotosAuthenticationError(
                    'Forbidden: API key may not have necessary permissions.'
                )
            elif response.status_code == 404:
                raise PhotosNotFoundError(f'Resource not found: {endpoint}')
            elif response.status_code == 429:
                raise PhotosRateLimitError('Rate limit exceeded.')
            else:
                raise PhotosAPIError(
                    f'Unexpected error {response.status_code}: {response.text}'
                )

    async def search_random_photo(
        self,
        query: str,
        per_page: int = 1,
        page: int = 1,
    ) -> SearchResponse:
        """Search a random photo asynchronously."""
        data = await self._request(
            'search',
            params={'query': query, 'per_page': per_page, 'page': page},
        )
        if data.get('total_results', 0) == 0:
            raise PhotosNoResultsError(
                f"There are no photos for search term '{query}'."
            )

        photos = data.get('photos', [])
        if not photos:
            raise PhotosNotFoundError('No photos found.')

        return PexelsSearchResponse(**data).get_search_response()
