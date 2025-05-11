from unittest.mock import MagicMock, patch

import pytest

from germanki.photos import SearchResponse
from germanki.photos.exceptions import (
    PhotosAPIError,
    PhotosAuthenticationError,
    PhotosNoResultsError,
    PhotosNotFoundError,
)
from germanki.photos.pexels import (
    PexelsClient,
    PexelsSearchResponse,
)


@pytest.fixture()
def client():
    return PexelsClient(api_key='test_key')


def test_client_init():
    assert PexelsClient(api_key='test_key').api_key == 'test_key'


@patch('requests.get')
def test_client_init_no_api_key(mock_get, monkeypatch):
    monkeypatch.delenv('PEXELS_API_KEY', raising=False)
    with pytest.raises(PhotosAuthenticationError):
        PexelsClient()


def test_headers(client: PexelsClient):
    assert client.headers == {'Authorization': 'test_key'}


@patch('requests.get')
def test_request_success(mock_get, client: PexelsClient):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'photos': [],
        'total_results': 10,
    }
    response = client._request('search', {'query': 'nature'})
    assert response == {'photos': [], 'total_results': 10}
    mock_get.assert_called_once()


@pytest.mark.parametrize(
    'status_code, exception',
    [
        (401, PhotosAuthenticationError),
        (403, PhotosAuthenticationError),
        (404, PhotosNotFoundError),
        (500, PhotosAPIError),
    ],
)
@patch('requests.get')
def test_request_errors(
    mock_get, client: PexelsClient, status_code, exception
):
    mock_get.return_value.status_code = status_code
    mock_get.return_value.text = 'Error'
    with pytest.raises(exception):
        client._request('search')


@patch('requests.get')
def test_request_rate_limit_retry(mock_get, client: PexelsClient):
    mock_get.side_effect = [
        MagicMock(status_code=429, text='Rate limit exceeded'),
        MagicMock(status_code=429, text='Rate limit exceeded'),
        MagicMock(
            status_code=200, json=lambda: {'photos': [], 'total_results': 10}
        ),
    ]
    response = client._request('search', {'query': 'nature'})
    assert response == {'photos': [], 'total_results': 10}
    assert mock_get.call_count == 3


@patch('requests.get')
def test_search_random_photo_success(mock_get, client: PexelsClient):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'photos': [{'src': {'large2x': 'image_url'}}],
        'total_results': 1,
    }
    response = client.search_random_photo('nature')
    assert isinstance(response, SearchResponse)
    assert response.total_results == 1
    assert response.photo_urls[0] == 'image_url'


@patch('requests.get')
def test_search_random_photo_no_results(mock_get, client: PexelsClient):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'photos': [],
        'total_results': 0,
    }
    with pytest.raises(PhotosNoResultsError):
        client.search_random_photo('invalid_query')


@patch('requests.get')
def test_search_random_photo_empty_photos_list(mock_get, client: PexelsClient):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'photos': [],
        'total_results': 10,
    }
    with pytest.raises(PhotosNotFoundError):
        client.search_random_photo('empty_query')
