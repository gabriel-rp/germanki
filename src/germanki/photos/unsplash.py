import os
from typing import Any, Final

import httpx

from germanki.photos import PhotosClient, SearchResponse
from germanki.photos.exceptions import (
    PhotosAPIError,
    PhotosAuthenticationError,
    PhotosNoResultsError,
    PhotosNotFoundError,
    PhotosRateLimitError,
)


class UnsplashClient(PhotosClient):
    BASE_URL: Final[str] = 'https://api.unsplash.com/'

    def __init__(self, api_key: str | None = None):
        super().__init__(api_key or os.getenv('UNSPLASH_API_KEY'))

    @property
    def headers(self):
        if not self.api_key:
            raise PhotosAuthenticationError('Unsplash API key is missing.')
        return {'Authorization': f'Client-ID {self.api_key}'}

    async def _request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
        self, query: str, per_page: int = 1, page: int = 1
    ) -> SearchResponse:
        data = await self._request(
            'search/photos',
            params={'query': query, 'per_page': per_page, 'page': page},
        )
        if not data.get('results', []):
            raise PhotosNoResultsError(
                f"There are no photos for search term '{query}'."
            )

        return SearchResponse(
            photo_urls=[photo['urls']['full'] for photo in data['results']],
            total_results=data['total'],
        )
