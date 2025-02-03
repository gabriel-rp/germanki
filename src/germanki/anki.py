import base64
import json
from pathlib import Path
from typing import Dict, Optional

import requests
from pydantic.dataclasses import dataclass


@dataclass
class AnkiCard:
    front: str
    back: str
    extra: Optional[str] = ''
    front_audio: Optional[Path] = None
    back_audio: Optional[Path] = None
    front_image: Optional[Path] = None
    back_image: Optional[Path] = None
    card_speaker: Optional[Path] = None

    @property
    def front_audio_anki_filename(self) -> Optional[str]:
        return Path(self.front_audio).stem if self.front_audio else None

    @property
    def back_audio_anki_filename(self) -> Optional[str]:
        return Path(self.back_audio).stem if self.back_audio else None

    @property
    def front_image_anki_filename(self) -> Optional[str]:
        return Path(self.front_image).stem if self.front_image else None

    @property
    def back_image_anki_filename(self) -> Optional[str]:
        return Path(self.back_image).stem if self.back_image else None


class AnkiAPI:
    DEFAULT_BASE_URL = 'http://localhost:8765'

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url

    def _get_headers(self):
        return {
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _create_add_notes_payload_fields(
        anki_card: AnkiCard,
    ) -> Dict[str, str]:
        fields = {
            'Front': anki_card.front.replace('\n', '<br>'),
            'Back': anki_card.back.replace('\n', '<br>'),
            'Extra': anki_card.extra.replace('\n', '<br>'),
        }
        if anki_card.front_audio:
            fields[
                'Front'
            ] += f'<br>\n <audio controls autoplay src="{anki_card.front_audio_anki_filename}"></audio>'
        if anki_card.back_audio:
            fields[
                'Back'
            ] += f'<br>\n <audio controls autoplay src="{anki_card.back_audio_anki_filename}"></audio>'
        if anki_card.front_image:
            fields[
                'Front'
            ] += f'<br>\n <img src="{anki_card.front_image_anki_filename}" style="max-width: 500px;">'
        if anki_card.back_image:
            fields[
                'Back'
            ] += f'<br>\n <img src="{anki_card.back_image_anki_filename}" style="max-width: 500px;">'
        return fields

    @staticmethod
    def _create_add_notes_payload_params(
        deck_name: str, anki_card: AnkiCard
    ) -> Dict[str, str]:
        fields = AnkiAPI._create_add_notes_payload_fields(anki_card)
        return dict(
            notes=[
                {
                    'deckName': deck_name,
                    'modelName': 'Basic',
                    'fields': fields,
                    'tags': ['automated'],
                }
            ]
        )

    def _create_add_notes_payload(
        self, deck_name: str, anki_card: AnkiCard
    ) -> Dict[str, str]:
        params = AnkiAPI._create_add_notes_payload_params(deck_name, anki_card)
        payload = dict(
            action='addNotes',
            version=6,
            params=params,
        )
        return payload

    def add_card(
        self,
        deck_name: str,
        anki_card: AnkiCard,
        create_deck_if_not_exists: bool = True,
    ) -> None:
        deck_exists = self._deck_exists(deck_name)

        if not deck_exists:
            if not create_deck_if_not_exists:
                raise Exception(f'Deck {deck_name} does not exist')
            self._create_deck(deck_name)

        self._add_card(deck_name, anki_card)

    def _create_deck(self, deck_name: str) -> None:
        payload = dict(
            action='createDeck', version=6, params=dict(deck=deck_name)
        )
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            data=json.dumps(payload),
        )
        if response.status_code != 200:
            raise Exception(
                f'Request failed with status code {response.status_code}'
            )

    def _deck_exists(self, deck_name: str) -> bool:
        payload = dict(
            action='deckNames',
            version=6,
        )
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            data=json.dumps(payload),
        )
        if response.status_code != 200:
            raise Exception(
                f'Request failed with status code {response.status_code}'
            )

        result = response.json()['result']
        return deck_name in result

    def _add_card(self, deck_name: str, anki_card: AnkiCard) -> None:
        payload = self._create_add_notes_payload(deck_name, anki_card)

        self._add_card_media_files(
            anki_card.front_image, anki_card.front_image_anki_filename
        )
        self._add_card_media_files(
            anki_card.back_image, anki_card.back_image_anki_filename
        )
        self._add_card_media_files(
            anki_card.front_audio, anki_card.front_audio_anki_filename
        )
        self._add_card_media_files(
            anki_card.back_audio, anki_card.back_audio_anki_filename
        )

        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            data=json.dumps(payload),
        )
        if response.status_code != 200:
            raise Exception(
                f'Request failed with status code {response.status_code}'
            )

    def _create_store_media_file_payload(self, image_path: str, filename: str):
        return dict(
            action='storeMediaFile',
            version=6,
            params=dict(
                filename=filename,
                data=base64.b64encode(
                    Path(f'/{image_path}').read_bytes()
                ).decode('utf-8'),
            ),
        )

    def _add_card_media_files(self, path, filename) -> None:
        if not path:
            return
        payload = self._create_store_media_file_payload(path, filename)
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            data=json.dumps(payload),
        )
        if response.status_code != 200:
            raise Exception(
                f'Request failed with status code {response.status_code}'
            )
