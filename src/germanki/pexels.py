import os
from typing import Any, Dict, Generator, List, Optional

import requests
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class PhotoSource(BaseModel):
    large2x: str


class PhotoInfo(BaseModel):
    src: PhotoSource


class SearchResponse(BaseModel):
    photos: List[PhotoInfo]
    total_results: int


class PexelsAPIError(Exception):
    """Base exception for Pexels API errors."""

    pass


class PexelsRateLimitError(PexelsAPIError):
    """Raised when the API rate limit is exceeded."""

    pass


class PexelsAuthenticationError(PexelsAPIError):
    """Raised when API authentication fails."""

    pass


class PexelsNotFoundError(PexelsAPIError):
    """Raised when a requested resource is not found."""

    pass


class PexelsNoResultsError(PexelsAPIError):
    """Raised when no results are found for a search query."""

    pass


class PexelsClient:
    BASE_URL = 'https://api.pexels.com/v1/'

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('PEXELS_API_KEY')
        if not self.api_key:
            raise PexelsAuthenticationError(
                'API key is required. Set PEXELS_API_KEY environment variable or pass it explicitly.'
            )

    @property
    def headers(self):
        return {'Authorization': self.api_key}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(PexelsRateLimitError),
    )
    def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handles API requests with retry logic on rate limiting."""
        url = f'{self.BASE_URL}{endpoint}'
        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise PexelsAuthenticationError(
                'Invalid API key or unauthorized access.'
            )
        elif response.status_code == 403:
            raise PexelsAuthenticationError(
                'Forbidden: API key may not have necessary permissions.'
            )
        elif response.status_code == 404:
            raise PexelsNotFoundError(f'Resource not found: {endpoint}')
        elif response.status_code == 429:
            raise PexelsRateLimitError('Rate limit exceeded. Retrying...')
        else:
            raise PexelsAPIError(
                f'Unexpected error {response.status_code}: {response.text}'
            )

    def search_random_photo(
        self,
        query: str,
        per_page: int = 1,
        page: int = 1,
        orientation: str = 'square',
    ) -> Generator[SearchResponse, None, None]:
        """Search a random photo with the given query."""
        data = self._request(
            'search',
            params={
                'query': query,
                'per_page': per_page,
                'page': page,
                'orientation': orientation,
            },
        )
        if data.get('total_results', 0) == 0:
            raise PexelsNoResultsError(
                f"There are no photos for search term '{query}'."
            )

        photos = data.get('photos', [])
        if not photos:
            raise PexelsNotFoundError('No photos found.')

        return SearchResponse(**data)
