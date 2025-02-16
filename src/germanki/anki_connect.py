import base64
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field


class AnkiMediaType(Enum):
    IMAGE = 'image'
    AUDIO = 'audio'


class AnkiMedia(BaseModel):
    path: Path
    anki_media_type: AnkiMediaType

    @property
    def filename(self) -> str:
        return self.path.stem


class AnkiCard(BaseModel):
    front: str
    back: str
    extra: str = Field(default='')
    media: List[AnkiMedia] = Field(default=[])


class AnkiConnectError(Exception):
    """Base exception for AnkiConnect errors."""

    pass


class AnkiConnectRequestError(AnkiConnectError):
    """Exception raised for request failures (e.g., connection issues)."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(
            f'Request failed: {message} (Status Code: {status_code})'
        )


class AnkiConnectResponseError(AnkiConnectError):
    """Exception raised when AnkiConnect returns an error response."""

    def __init__(self, action: str, error: str):
        super().__init__(f"AnkiConnect error on action '{action}': {error}")


class AnkiConnectDeckNotExistsError(AnkiConnectError):
    def __init__(self, deck_name: str):
        self.deck_name = deck_name
        super().__init__(f"Deck '{deck_name}' does not exist.")


class AnkiConnectClient:
    """Client for interacting with the AnkiConnect API."""

    def __init__(
        self,
        host: str = 'http://localhost',
        port: int = 8765,
        version: int = 6,
        timeout: int = 5,
        default_tags: List[str] = None,
    ):
        self.base_url = f'{host}:{port}'
        self.version = version
        self.timeout = timeout
        self.session = None
        self.default_tags = (
            default_tags
            if default_tags
            else [
                'automated',
                datetime.now().strftime('%Y-%m-%d'),
            ]
        )

    def _request(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Internal method to send a request to AnkiConnect."""
        payload = {
            'action': action,
            'version': self.version,
            'params': params or {},
        }

        try:
            with self.get_session() as session:
                response = session.post(
                    self.base_url, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
        except requests.RequestException as e:
            raise AnkiConnectRequestError(
                str(e), getattr(e.response, 'status_code', None)
            )

        data = response.json()

        if 'error' in data and data['error']:
            raise AnkiConnectResponseError(action, data['error'])

        return data.get('result')

    def _add_note_payload_params(
        self,
        deck_name: str,
        anki_card: AnkiCard,
        tags: Optional[List[str]],
        model: str,
        allow_duplicate: bool,
    ) -> Dict[str, str]:
        tags = tags if tags else []
        return {
            'deckName': deck_name,
            'modelName': model,
            'fields': {
                'Front': anki_card.front,
                'Back': anki_card.back,
                'Extra': anki_card.extra,
            },
            'tags': self.default_tags + tags,
            'options': {'allowDuplicate': allow_duplicate},
        }

    def add_card(
        self,
        deck_name: str,
        anki_card: AnkiCard,
        tags: Optional[List[str]] = None,
        model: str = 'Basic',
        allow_duplicate: bool = False,
        create_deck_if_not_exists: bool = True,
    ) -> Dict[str, Any]:
        """Adds one card."""
        deck_exists = self._deck_exists(deck_name)
        if not deck_exists:
            if not create_deck_if_not_exists:
                raise AnkiConnectDeckNotExistsError(deck_name=deck_name)
            self._create_deck(deck_name)

        self.upload_media_from_card(anki_card)

        return self._request(
            'addNote',
            {
                'note': self._add_note_payload_params(
                    deck_name, anki_card, tags, model, allow_duplicate
                )
            },
        )

    def _create_deck(self, deck_name: str) -> Dict[str, Any]:
        return self._request('createDeck', {'deck': deck_name})

    def _deck_exists(self, deck_name: str) -> bool:
        decks = self._request('deckNames')
        return decks is not None and deck_name in decks

    def upload_media(self, anki_media: AnkiMedia) -> Dict[str, Any]:
        """Uploads a media file (image or audio) to Anki."""

        if not anki_media.path.exists():
            raise FileNotFoundError(f'File not found: {anki_media.path}')

        params = {
            'filename': anki_media.filename,
            'data': base64.b64encode(anki_media.path.read_bytes()).decode(
                'utf-8'
            ),
        }
        return self._request('storeMediaFile', params)

    def upload_media_from_card(
        self, anki_card: AnkiCard
    ) -> List[Dict[str, Any]]:
        return [self.upload_media(media) for media in anki_card.media]

    def get_session(self) -> requests.Session:
        if self.session is not None:
            return self.session

        return requests.Session()

    def __enter__(self):
        self.session = self.get_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
