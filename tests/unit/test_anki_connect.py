from pathlib import Path
from unittest.mock import patch

import pytest

from germanki.anki_connect import (
    AnkiCard,
    AnkiConnectClient,
    AnkiConnectDeckNotExistsError,
    AnkiConnectRequestError,
    AnkiConnectResponseError,
    AnkiMedia,
    AnkiMediaType,
)


@pytest.fixture()
def anki_client():
    return AnkiConnectClient()


@pytest.fixture()
def deck_name():
    return 'Test Deck'


@pytest.fixture()
def test_card():
    return AnkiCard(
        front='Front Content',
        back='Back Content',
    )


@pytest.fixture()
def test_card_with_media():
    return AnkiCard(
        front='Front Content',
        back='Back Content',
        media=[
            AnkiMedia(
                path=Path('test.jpg'),
                extension='jpg',
                anki_media_type=AnkiMediaType.IMAGE,
            ),
            AnkiMedia(
                path=Path('test.mp3'),
                extension='mp3',
                anki_media_type=AnkiMediaType.AUDIO,
            ),
        ],
    )


def test_anki_connect_client_init():
    client = AnkiConnectClient()
    assert client.base_url == 'http://localhost:8765'
    assert client.timeout == 5
    assert client.default_tags == ['automated']

    client = AnkiConnectClient(host='http://custom_host', port=1234, version=7)
    assert client.base_url == 'http://custom_host:1234'
    assert client.version == 7


@patch('requests.Session.post')
def test_request_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'result': 'success'}
    client = AnkiConnectClient()
    result = client._request('some_action')
    assert result == 'success'


@patch('requests.Session.post')
def test_request_failure(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.json.return_value = {
        'error': 'Internal Server Error'
    }
    client = AnkiConnectClient()
    with pytest.raises(AnkiConnectResponseError):
        client._request('some_action')


@patch('requests.Session.post')
def test_add_card_deck_not_exists(
    mock_post, anki_client: AnkiConnectClient, deck_name, test_card
):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'result': None}
    with pytest.raises(AnkiConnectDeckNotExistsError):
        anki_client.add_card(
            deck_name, test_card, create_deck_if_not_exists=False
        )


@patch('requests.Session.post')
def test_add_card_with_custom_tags(
    mock_post, anki_client: AnkiConnectClient, deck_name, test_card
):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'result': None}
    tags = ['tag1', 'tag2']
    anki_client.add_card(deck_name, test_card, tags=tags)
    payload = mock_post.call_args[1]['json']
    assert 'tag1' in payload['params']['note']['tags']
    assert 'tag2' in payload['params']['note']['tags']


@patch('requests.Session.post')
@patch('pathlib.Path.read_bytes')
def test_upload_media_file_not_found(
    mock_read_bytes, mock_post, anki_client: AnkiConnectClient
):
    mock_read_bytes.return_value = b'fake_data'
    mock_post.return_value.status_code = 200
    with pytest.raises(FileNotFoundError):
        anki_client.upload_media(
            AnkiMedia(
                path=Path('non_existent_file.jpg'),
                extension='jpg',
                anki_media_type=AnkiMediaType.IMAGE,
            )
        )


@patch('pathlib.Path.exists')
@patch('requests.Session.post')
@patch('pathlib.Path.read_bytes')
def test_upload_media(
    mock_read_bytes, mock_post, mock_exists, anki_client: AnkiConnectClient
):
    mock_exists.return_value = True
    mock_read_bytes.return_value = b'image_data'
    mock_post.return_value.status_code = 200
    result = anki_client.upload_media(
        AnkiMedia(
            path=Path('image.jpg'),
            extension='jpg',
            anki_media_type=AnkiMediaType.IMAGE,
        )
    )
    assert mock_post.call_count == 1
    assert result is not None


@patch('requests.Session.post')
@patch('pathlib.Path.read_bytes')
def test_upload_media_file_does_not_exist(
    mock_read_bytes, mock_post, anki_client: AnkiConnectClient
):
    mock_read_bytes.return_value = b'image_data'
    mock_post.return_value.status_code = 200
    with pytest.raises(FileNotFoundError):
        anki_client.upload_media(
            AnkiMedia(
                path=Path('image.jpg'),
                extension='jpg',
                anki_media_type=AnkiMediaType.IMAGE,
            )
        )


def test_add_note_payload_params_with_tags_and_model(
    anki_client: AnkiConnectClient, deck_name, test_card
):
    tags = ['custom_tag']
    model = 'Basic'
    allow_duplicate = True
    payload = anki_client._add_note_payload_params(
        deck_name, test_card, tags, model, allow_duplicate
    )
    assert payload['tags'] == ['automated', 'custom_tag']
    assert payload['modelName'] == model
    assert payload['options']['allowDuplicate'] == allow_duplicate
