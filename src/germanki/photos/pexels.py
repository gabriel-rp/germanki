import os
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel
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
from germanki.utils import get_logger

logger = get_logger(__file__)


class PexelsPhotoSource(BaseModel):
    large2x: str


class PexelsPhotoInfo(BaseModel):
    src: PexelsPhotoSource


class PexelsSearchResponse(BaseModel):
    photos: List[PexelsPhotoInfo]
    total_results: int

    def get_search_response(self) -> SearchResponse:
        return SearchResponse(
            photo_urls=[photo.src.large2x for photo in self.photos],
            total_results=self.total_results,
        )


class PexelsClient(PhotosClient):
    BASE_URL = 'https://api.pexels.com/v1/'

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('PEXELS_API_KEY')
        if not self.api_key:
            raise PhotosAuthenticationError(
                'API key is required. Set PEXELS_API_KEY environment variable or pass it explicitly.'
            )

    @property
    def headers(self):
        return {'Authorization': self.api_key}

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(PhotosRateLimitError),
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
            exception = PhotosRateLimitError(
                'Rate limit exceeded. Retrying...'
            )
            logger.info(exception)
            raise exception
        else:
            raise PhotosAPIError(
                f'Unexpected error {response.status_code}: {response.text}'
            )

    def search_random_photo(
        self,
        query: str,
        per_page: int = 1,
        page: int = 1,
    ) -> SearchResponse:
        """Search a random photo with the given query."""
        data = self._request(
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
