import pytest
import respx
import httpx
from germanki.photos import SearchResponse
from germanki.photos.pexels import PexelsClient
from germanki.photos.exceptions import (
    PhotosAuthenticationError,
    PhotosNotFoundError,
    PhotosRateLimitError,
    PhotosAPIError,
    PhotosNoResultsError
)


@pytest.fixture
def pexels_client():
    return PexelsClient(api_key='test_key')


@pytest.mark.asyncio
@respx.mock
async def test_search_random_photo_success(pexels_client):
    respx.get("https://api.pexels.com/v1/search").mock(return_value=httpx.Response(200, json={
        'photos': [{'src': {'large2x': 'https://example.com/photo.jpg'}}],
        'total_results': 1
    }))
    
    response = await pexels_client.search_random_photo('query')
    assert isinstance(response, SearchResponse)
    assert response.photo_urls == ['https://example.com/photo.jpg']
    assert response.total_results == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_random_photo_no_results(pexels_client):
    respx.get("https://api.pexels.com/v1/search").mock(return_value=httpx.Response(200, json={
        'photos': [],
        'total_results': 0
    }))
    
    with pytest.raises(PhotosNoResultsError):
        await pexels_client.search_random_photo('query')


@pytest.mark.asyncio
@respx.mock
async def test_request_authentication_error(pexels_client):
    respx.get("https://api.pexels.com/v1/test").mock(return_value=httpx.Response(401))
    with pytest.raises(PhotosAuthenticationError):
        await pexels_client._request('test')


@pytest.mark.asyncio
@respx.mock
async def test_request_not_found_error(pexels_client):
    respx.get("https://api.pexels.com/v1/test").mock(return_value=httpx.Response(404))
    with pytest.raises(PhotosNotFoundError):
        await pexels_client._request('test')


@pytest.mark.asyncio
@respx.mock
async def test_request_rate_limit_error(pexels_client):
    respx.get("https://api.pexels.com/v1/test").mock(return_value=httpx.Response(429))
    with pytest.raises(PhotosRateLimitError):
        await pexels_client._request('test')


@pytest.mark.asyncio
@respx.mock
async def test_request_api_error(pexels_client):
    respx.get("https://api.pexels.com/v1/test").mock(return_value=httpx.Response(500))
    with pytest.raises(PhotosAPIError):
        await pexels_client._request('test')
