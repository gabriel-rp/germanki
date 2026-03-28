import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
import httpx

from germanki.anki_connect import (
    AnkiCard,
    AnkiConnectClient,
    AnkiConnectDeckNotExistsError,
    AnkiConnectResponseError,
    AnkiConnectRequestError,
    AnkiMedia,
    AnkiMediaType,
)


@pytest.fixture()
def anki_client():
    return AnkiConnectClient(default_tags=['automated'])


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
                anki_media_type=AnkiMediaType.IMAGE,
            ),
            AnkiMedia(
                path=Path('test.mp3'),
                anki_media_type=AnkiMediaType.AUDIO,
            ),
        ],
    )


def test_anki_connect_client_init():
    client = AnkiConnectClient(default_tags=['automated'])
    assert client.base_url == 'http://localhost:8765'
    assert client.timeout == 5
    assert client.default_tags == ['automated']

    client = AnkiConnectClient(host='http://custom_host', port=1234, version=7)
    assert client.base_url == 'http://custom_host:1234'
    assert client.version == 7


@pytest.mark.asyncio
@respx.mock
async def test_request_success(anki_client):
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={'result': 'success', 'error': None}))
    result = await anki_client._request('some_action')
    assert result == 'success'


@pytest.mark.asyncio
@respx.mock
async def test_request_failure(anki_client):
    # If AnkiConnect returns 500, httpx.raise_for_status() will raise HTTPStatusError,
    # which _request catches and wraps in AnkiConnectRequestError.
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(500))
    with pytest.raises(AnkiConnectRequestError):
        await anki_client._request('some_action')


@pytest.mark.asyncio
@respx.mock
async def test_request_anki_error(anki_client):
    # If AnkiConnect returns 200 but with an 'error' field in JSON
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={
        'result': None,
        'error': 'Some Anki Error'
    }))
    with pytest.raises(AnkiConnectResponseError):
        await anki_client._request('some_action')


@pytest.mark.asyncio
@respx.mock
async def test_add_card_deck_not_exists(
    anki_client: AnkiConnectClient, deck_name, test_card
):
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={'result': [], 'error': None}))
    with pytest.raises(AnkiConnectDeckNotExistsError):
        await anki_client.add_card(
            deck_name, test_card, create_deck_if_not_exists=False
        )


@pytest.mark.asyncio
@respx.mock
async def test_add_card_with_custom_tags(
    anki_client: AnkiConnectClient, deck_name, test_card
):
    # Match deckNames
    respx.post("http://localhost:8765").mock(
        side_effect=lambda request: httpx.Response(200, json={'result': [deck_name], 'error': None}) 
        if json.loads(request.content).get('action') == 'deckNames' 
        else httpx.Response(200, json={'result': 12345, 'error': None})
    )
    
    tags = ['tag1', 'tag2']
    await anki_client.add_card(deck_name, test_card, tags=tags)



@pytest.mark.asyncio
@respx.mock
async def test_add_card_with_media_file_not_found(
    anki_client: AnkiConnectClient, deck_name, test_card_with_media
):
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={'result': [deck_name], 'error': None}))
    with pytest.raises(FileNotFoundError):
        await anki_client.add_card(deck_name, test_card_with_media)


@pytest.mark.asyncio
@respx.mock
@patch('pathlib.Path.exists')
@patch('pathlib.Path.read_bytes')
async def test_add_card_success_with_media(
    mock_read_bytes,
    mock_exists,
    anki_client: AnkiConnectClient,
    deck_name,
    test_card_with_media,
):
    mock_exists.return_value = True
    mock_read_bytes.return_value = b'image_data'
    
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={'result': [deck_name], 'error': None}))
    
    await anki_client.add_card(deck_name, test_card_with_media)
    assert len(respx.calls) >= 4


@pytest.mark.asyncio
@respx.mock
@patch('pathlib.Path.read_bytes')
async def test_upload_media_file_not_found(
    mock_read_bytes, anki_client: AnkiConnectClient
):
    mock_read_bytes.return_value = b'fake_data'
    with pytest.raises(FileNotFoundError):
        await anki_client.upload_media(
            AnkiMedia(
                path=Path('non_existent_file.jpg'),
                anki_media_type=AnkiMediaType.IMAGE,
            )
        )


@pytest.mark.asyncio
@respx.mock
@patch('pathlib.Path.exists')
@patch('pathlib.Path.read_bytes')
async def test_upload_media(
    mock_read_bytes, mock_exists, anki_client: AnkiConnectClient
):
    mock_exists.return_value = True
    mock_read_bytes.return_value = b'image_data'
    respx.post("http://localhost:8765").mock(return_value=httpx.Response(200, json={'result': 'success', 'error': None}))
    
    result = await anki_client.upload_media(
        AnkiMedia(
            path=Path('image.jpg'),
            anki_media_type=AnkiMediaType.IMAGE,
        )
    )
    assert result == 'success'


@pytest.mark.asyncio
@respx.mock
async def test_get_model_names(anki_client):
    respx.post("http://localhost:8765").mock(
        return_value=httpx.Response(200, json={'result': ['Basic', 'germanki_card'], 'error': None})
    )
    result = await anki_client.get_model_names()
    assert result == ['Basic', 'germanki_card']


@pytest.mark.asyncio
@respx.mock
async def test_create_model(anki_client):
    respx.post("http://localhost:8765").mock(
        return_value=httpx.Response(200, json={'result': {'name': 'germanki_card'}, 'error': None})
    )
    result = await anki_client.create_model(
        model_name="germanki_card",
        in_order_fields=["Front", "Back", "Extra"],
        card_templates=[{"Name": "Card 1", "Front": "{{Front}}", "Back": "{{Back}}"}],
    )
    assert result['name'] == 'germanki_card'


@pytest.mark.asyncio
@respx.mock
@patch('pathlib.Path.read_bytes')
async def test_upload_media_file_does_not_exist_trigger(
    mock_read_bytes, anki_client: AnkiConnectClient
):
    mock_read_bytes.return_value = b'image_data'
    with pytest.raises(FileNotFoundError):
        await anki_client.upload_media(
            AnkiMedia(
                path=Path('image.jpg'),
                anki_media_type=AnkiMediaType.IMAGE,
            )
        )


def test_add_note_payload_params_with_tags_and_model(
    anki_client: AnkiConnectClient, deck_name, test_card
):
    tags = ['custom_tag']
    model = 'germanki_card'
    allow_duplicate = True
    payload = anki_client._add_note_payload_params(
        deck_name, test_card, tags, model, allow_duplicate
    )
    assert payload['tags'] == ['automated', 'custom_tag']
    assert payload['modelName'] == model
    assert payload['options']['allowDuplicate'] == allow_duplicate
