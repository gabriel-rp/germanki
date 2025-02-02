import base64
from unittest.mock import patch

import pytest

from germanki.anki import AnkiAPI, AnkiCard


@pytest.fixture
def anki_api():
    return AnkiAPI()


@pytest.fixture
def deck_name():
    return 'my_deck'


@pytest.fixture
def test_card():
    return AnkiCard(front='Hallo', back='Hello')


@pytest.fixture
def test_card_with_media_resources():
    return AnkiCard(
        front='Hallo',
        back='Hello',
        front_audio='path/to/audio.mp3',
        back_image='path/to/image.jpg',
    )


@patch('requests.post')
def test_create_deck(mock_post, anki_api, deck_name):
    mock_post.return_value.status_code = 200
    anki_api._create_deck(deck_name)
    mock_post.assert_called_once()


@patch('requests.post')
def test_create_deck_failure(mock_post, anki_api, deck_name):
    mock_post.return_value.status_code = 500
    with pytest.raises(Exception):
        anki_api._create_deck(deck_name)


@patch('requests.post')
def test_deck_exists(mock_post, anki_api, deck_name):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'result': [deck_name]}
    assert anki_api._deck_exists(deck_name)

    mock_post.return_value.json.return_value = {'result': []}
    assert not anki_api._deck_exists(deck_name)


@patch('requests.post')
def test_deck_exists_failure(mock_post, anki_api, deck_name):
    mock_post.return_value.status_code = 500
    with pytest.raises(Exception):
        anki_api._deck_exists(deck_name)


@patch('requests.post')
def test_add_card(mock_post, anki_api, deck_name, test_card):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {'result': None}
    anki_api._add_card(deck_name, test_card)
    assert mock_post.call_count == 1


@patch('requests.post')
def test_add_card_failure(mock_post, anki_api, test_card, deck_name):
    mock_post.return_value.status_code = 500
    with pytest.raises(Exception):
        anki_api._add_card(deck_name, test_card)


@patch('pathlib.Path.read_bytes')
@patch('requests.post')
def test_add_card_with_media(
    mock_post,
    mock_read_bytes,
    anki_api,
    deck_name,
    test_card_with_media_resources,
):
    mock_read_bytes.return_value = b'test data'
    mock_post.return_value.status_code = 200
    anki_api._add_card(deck_name, test_card_with_media_resources)
    # media resources uploaded first
    assert mock_post.call_count == 3


@patch('pathlib.Path.read_bytes')
@patch('requests.post')
def test_add_card_media_files(mock_post, mock_read_bytes, anki_api):
    mock_read_bytes.return_value = b'image data'
    mock_post.return_value.status_code = 200
    anki_api._add_card_media_files('src/image.jpg', 'image.jpg')
    mock_post.assert_called_once()


@patch('pathlib.Path.read_bytes')
@patch('requests.post')
def test_add_card_media_files_failure(mock_post, mock_read_bytes, anki_api):
    mock_read_bytes.return_value = b'image data'
    mock_post.return_value.status_code = 500
    with pytest.raises(Exception):
        anki_api._add_card_media_files('src/image.jpg', 'image.jpg')


def test_create_add_notes_payload(anki_api, deck_name, test_card):
    payload = anki_api._create_add_notes_payload(deck_name, test_card)
    assert payload['action'] == 'addNotes'
    assert payload['params']['notes'][0]['deckName'] == deck_name


@patch('pathlib.Path.read_bytes')
def test_create_store_media_file_payload(mock_read_bytes, anki_api):
    mock_read_bytes.return_value = b'test data'

    payload = anki_api._create_store_media_file_payload(
        'src/image.jpg', 'image.jpg'
    )
    assert payload['action'] == 'storeMediaFile'
    assert payload['params']['filename'] == 'image.jpg'
    assert payload['params']['data'] == base64.b64encode(b'test data').decode(
        'utf-8'
    )
