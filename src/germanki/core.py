import os
from operator import le
from pathlib import Path
from random import randint
from typing import List, Optional

import requests
from pydantic import BaseModel, Field

import germanki
from germanki.anki_connect import (
    AnkiCard,
    AnkiConnectClient,
    AnkiMedia,
    AnkiMediaType,
)
from germanki.config import Config
from germanki.pexels import PexelsClient, SearchResponse
from germanki.tts_mp3 import TTSAPI


class MediaUpdateException(Exception):
    pass


class AnkiCardInfo(BaseModel):
    # front
    word: str
    # back
    translations: List[str]
    # extra
    definition: str
    examples: List[str]
    extra: str
    one_word_summary: Optional[str] = Field(default=None)
    translation_image_url: Optional[str] = Field(default=None)
    word_audio_url: Optional[str] = Field(default=None)
    speaker: str = Field(default='Vicki')

    @property
    def query_word(self) -> str:
        return (
            self.one_word_summary
            if self.one_word_summary
            else self.translations[0]
        )


class AnkiCardHTMLPreview(AnkiCard):
    front: str
    back: str
    extra: str


class AnkiCardCreator:
    @staticmethod
    def front(
        card_contents: AnkiCardInfo,
        audio: AnkiMedia,
        path: str,
        autoplay: bool = True,
        style: str = '',
    ) -> str:
        autoplay_controls = 'autoplay' if autoplay else ''
        return (
            f'{card_contents.word}<br>'
            f'<audio controls {autoplay_controls} src="{path}" style="{style}"></audio>'
            if audio
            else ''
        )

    @staticmethod
    def back(
        card_contents: AnkiCardInfo,
        image: AnkiMedia,
        path: str,
        style: str = '',
    ) -> str:
        return (
            ', '.join(card_contents.translations)
            + (f'<br><img src="{path}" style="{style}">')
            if image
            else ''
        )

    @staticmethod
    def extra(card_contents: AnkiCardInfo) -> str:
        return (
            f'{card_contents.extra}<br><br>'
            f'Erklärung: {card_contents.definition}<br><br>'
            'Beispiele:<br>'
            f"{'<br>'.join([f'{ix+1}. {item}' for ix, item in enumerate(card_contents.examples)])}"
        )

    @staticmethod
    def create(card_contents: AnkiCardInfo) -> AnkiCard:
        audio = (
            AnkiMedia(
                anki_media_type=AnkiMediaType.AUDIO,
                path=card_contents.word_audio_url,
                extension='mp3',
            )
            if card_contents.word_audio_url
            else None
        )
        image = (
            AnkiMedia(
                anki_media_type=AnkiMediaType.IMAGE,
                path=card_contents.translation_image_url,
                extension='jpg',
            )
            if card_contents.translation_image_url
            else None
        )
        return AnkiCard(
            front=AnkiCardCreator.front(card_contents, audio, audio.filename),
            back=AnkiCardCreator.back(
                card_contents, image, image.filename, style='max-width: 500px;'
            ),
            extra=AnkiCardCreator.extra(card_contents),
            media=[audio, image],
        )

    @staticmethod
    def html_preview(card_contents: AnkiCardInfo) -> AnkiCardHTMLPreview:
        audio = None
        image = None
        audio_path = None
        image_path = None
        host = os.getenv('STREAMLIT_SERVER_ADDRESS', 'localhost')
        port = os.getenv('STREAMLIT_SERVER_PORT', '8501')

        if card_contents.word_audio_url:
            audio = AnkiMedia(
                anki_media_type=AnkiMediaType.AUDIO,
                path=card_contents.word_audio_url,
                extension='mp3',
            )
            audio_path = f'http://{host}:{port}/app/{audio.path.relative_to(Path(germanki.__file__).parent)}'
        if card_contents.translation_image_url:
            image = AnkiMedia(
                anki_media_type=AnkiMediaType.IMAGE,
                path=card_contents.translation_image_url,
                extension='jpg',
            )
            image_path = f'http://{host}:{port}/app/{image.path.relative_to(Path(germanki.__file__).parent)}'
        return AnkiCardHTMLPreview(
            front=AnkiCardCreator.front(
                card_contents,
                audio,
                path=audio_path,
                autoplay=False,
                style='width: 100%;',
            ),
            back=AnkiCardCreator.back(
                card_contents,
                image,
                path=image_path,
            ),
            extra=AnkiCardCreator.extra(card_contents),
        )


class ImageDownloader:
    @staticmethod
    def download_image(
        query: str,
        pexels_api_key: str,
        file_path: Path,
        page: int,
        per_page: int = 1,
    ) -> None:
        pexels_client = PexelsClient(pexels_api_key)
        search_response: SearchResponse = pexels_client.search_random_photo(
            query=query,
            per_page=per_page,
            page=page,
            orientation='square',
        )
        response = requests.get(search_response.photos[0].src.medium)

        if response.status_code != 200 or not response.content:
            raise Exception(f'Error downloading image: {response.status_code}')

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


class Germanki:
    _selected_speaker: str
    _card_contents: List[AnkiCardInfo]

    def __init__(self, config: Config = Config()):
        self.config = config
        self.selected_speaker = self.default_speaker
        self._card_contents = []

    @property
    def card_contents(self) -> List[AnkiCardInfo]:
        return self._card_contents

    @card_contents.setter
    def card_contents(self, card_contents: List[AnkiCardInfo]):
        self._card_contents = card_contents
        for index in range(len(card_contents)):
            self.update_card_media(index)

    @property
    def speakers(self) -> List[str]:
        return [speaker.value for speaker in self.config.speakers]

    @property
    def default_speaker(self) -> List[str]:
        return str(self.config.default_speaker.value)

    @property
    def selected_speaker(self) -> str:
        return self._selected_speaker

    @selected_speaker.setter
    def selected_speaker(self, speaker: str):
        if speaker not in self.speakers:
            raise ValueError('Invalid speaker.')
        self._selected_speaker = speaker

    def update_card_media(self, index: int) -> None:
        card = self._card_contents[index]

        errors = []
        try:
            card.translation_image_url = self._get_image(card.query_word)
        except Exception as e:
            errors.append(e)
        try:
            card.word_audio_url = self._get_tts_audio(card.word)
        except Exception as e:
            errors.append(e)

        if len(errors) > 0:
            raise MediaUpdateException(
                f'Could not update card media. Errors: {[str(error) for error in errors]}'
            )

    def create_cards(self, deck_name: str):
        anki_client = AnkiConnectClient()
        for card_contents in self._card_contents:
            card = AnkiCardCreator.create(card_contents)
            self._create_card(
                deck_name=deck_name, anki_client=anki_client, anki_card=card
            )

    def _create_card(
        self,
        deck_name: str,
        anki_client: AnkiConnectClient,
        anki_card: AnkiCardInfo,
    ):
        anki_client.add_card(
            deck_name=deck_name,
            anki_card=anki_card,
        )

    def _get_image(self, query: str, max_pages: int = 100) -> Optional[Path]:
        page = randint(1, max_pages)
        image_path = self.config.image_filepath(
            Germanki.convert_query_to_filename(f'{query}_{page}', ext='jpg')
        )
        if image_path.exists():
            return image_path

        ImageDownloader.download_image(
            query,
            pexels_api_key=self.config.pexels_api_key,
            file_path=image_path,
            page=page,
        )
        return image_path

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
        except Exception as e:
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
