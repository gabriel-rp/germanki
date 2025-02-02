from pathlib import Path
from random import randint
from typing import List, Optional

import requests
import yaml
from pydantic.dataclasses import dataclass

from germanki.anki import AnkiAPI, AnkiCard
from germanki.config import AudioPosition, Config, ImagePosition
from germanki.pexels import PexelsAPI
from germanki.tts_mp3 import TTSAPI


class ImageDownloader:
    @staticmethod
    def download_image(
        query: str,
        pexels_api_key: str,
        file_path: Path,
        page: int,
        per_page: int = 1,
    ) -> None:
        pexels_api = PexelsAPI(pexels_api_key)
        image_response = pexels_api.search_images(
            query=query,
            per_page=per_page,
            page=page,
            orientation='landscape',
        )
        if not image_response.success:
            raise Exception()

        response = requests.get(image_response.image_url)
        if not response.status_code == 200:
            raise Exception()

        with open(file_path, 'wb') as file:
            file.write(response.content)


class MP3Downloader:
    @staticmethod
    def download_mp3(msg: str, lang: str, file_path: Path) -> None:
        tts_api = TTSAPI()
        tts_response = tts_api.request_tts(msg=msg, lang=lang)
        if tts_response.success:
            if tts_api.download_mp3(
                mp3_url=tts_response.mp3_url, file_path=file_path
            ):
                pass
            else:
                raise Exception()
        else:
            raise Exception()


@dataclass
class CardResources:
    image: Optional[str] = None
    audio: Optional[str] = None


class Germanki:
    _cards: List[AnkiCard]
    _selected_speaker: str

    def __init__(self, config: Config = Config()):
        self.config = config
        self.selected_speaker = self.default_speaker

    @property
    def speakers(self) -> List[str]:
        return [speaker.value for speaker in self.config.speakers]

    @property
    def default_speaker(self) -> List[str]:
        return str(self.config.default_speaker.value)

    @property
    def cards(self) -> List[AnkiCard]:
        return self._cards

    @property
    def selected_speaker(self) -> str:
        return self._selected_speaker

    @selected_speaker.setter
    def selected_speaker(self, speaker: str):
        if speaker not in self.speakers:
            raise ValueError('Invalid speaker.')
        self._selected_speaker = speaker

    @cards.setter
    def cards(self, cards: str):
        self._cards = []
        cards_list = yaml.load(cards, Loader=yaml.Loader)
        for card_obj in cards_list:
            card = self.generate_card(
                card_obj.get('front'),
                card_obj.get('back'),
                card_obj.get('extra'),
            )
            self._cards.append(card)

    def refresh_card_images(self, index: int) -> None:
        old_card = self.cards[index]
        self.cards[index] = self.generate_card(
            old_card.front, old_card.back, old_card.extra
        )

    def generate_card(
        self, front: str, back: str, extra: Optional[str] = None
    ) -> AnkiCard:
        card = AnkiCard(
            front=front,
            back=back,
            extra=extra,
            card_speaker=self.selected_speaker,
        )
        image_path = self._get_image(card.back)
        audio_path = self._get_tts_audio(card.front)
        card.front_audio = (
            audio_path
            if self.config.audio_position
            in [AudioPosition.FRONT, AudioPosition.BOTH]
            else None
        )
        card.back_audio = (
            audio_path
            if self.config.audio_position
            in [AudioPosition.BACK, AudioPosition.BOTH]
            else None
        )
        card.front_image = (
            image_path
            if self.config.image_position
            in [ImagePosition.FRONT, ImagePosition.BOTH]
            else None
        )
        card.back_image = (
            image_path
            if self.config.image_position
            in [ImagePosition.BACK, ImagePosition.BOTH]
            else None
        )
        return card

    def create_cards(self, deck_name: str):
        anki_api = AnkiAPI()
        for card in self.cards:
            self._create_card(
                deck_name=deck_name, anki_api=anki_api, anki_card=card
            )

    def _create_card(
        self,
        deck_name: str,
        anki_api: AnkiAPI,
        anki_card: AnkiCard,
    ):
        anki_api.add_card(
            deck_name=deck_name,
            anki_card=anki_card,
        )

    def _get_image(self, query: str) -> Optional[Path]:
        page = randint(1, 100)
        image_path = self.config.image_filepath(
            Germanki.convert_query_to_filename(f'{query}_{page}', ext='jpg')
        )
        if image_path.exists():
            return image_path
        try:
            ImageDownloader.download_image(
                query,
                pexels_api_key=self.config.pexels_api_key,
                file_path=image_path,
                page=page,
            )
            return image_path
        except:
            return None

    def _get_tts_audio(self, query: str) -> Optional[Path]:
        audio_path = self.config.audio_filepath(
            Germanki.convert_query_to_filename(
                f'{query}_{self.selected_speaker}', ext='mp3'
            )
        )
        if audio_path.exists():
            return audio_path
        try:
            MP3Downloader.download_mp3(
                msg=query, lang=self.selected_speaker, file_path=audio_path
            )
            return audio_path
        except:
            return None

    @staticmethod
    def convert_query_to_filename(query: str, ext: str) -> str:
        # remove leading and trailing spaces
        query = query.strip()
        # replace spaces with underscores
        query = query.replace(' ', '_')
        # only commonly accepted characters in filename
        query = ''.join(c for c in query if c.isalnum() or c in ['_', '-'])
        # limit filename size
        query = query[:50]

        filename = f'{query}.{ext}'

        return filename
