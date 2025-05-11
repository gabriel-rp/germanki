import os
from typing import Any, Dict, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from germanki.photos import PhotosClient, SearchResponse
from germanki.photos.exceptions import (
    PhotosAPIError,
    PhotosAuthenticationError,
    PhotosNoResultsError,
    PhotosNotFoundError,
    PhotosRateLimitError,
)


class UnsplashClient(PhotosClient):
    BASE_URL = 'https://api.unsplash.com/'

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key or os.getenv('UNSPLASH_API_KEY'))
        if not self.api_key:
            raise PhotosAuthenticationError(
                'API key is required. Set UNSPLASH_API_KEY environment variable or pass it explicitly.'
            )

    @property
    def headers(self):
        return {'Authorization': f'Client-ID {self.api_key}'}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(PhotosRateLimitError),
    )
    def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f'{self.BASE_URL}{endpoint}'
        response = requests.get(url, headers=self.headers, params=params)

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
            raise PhotosRateLimitError('Rate limit exceeded. Retrying...')
        else:
            raise PhotosAPIError(
                f'Unexpected error {response.status_code}: {response.text}'
            )

    def search_random_photo(
        self, query: str, per_page: int = 1, page: int = 1
    ) -> SearchResponse:
        data = self._request(
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
