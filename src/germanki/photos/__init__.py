from abc import ABC, abstractmethod

from pydantic import BaseModel


class SearchResponse(BaseModel):
    photo_urls: list[str]
    total_results: int


class PhotosClient(ABC):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    @abstractmethod
    async def search_random_photo(
        self, query: str, per_page: int = 1, page: int = 1
    ) -> SearchResponse:
        """Abstract method for searching photos."""
        pass
