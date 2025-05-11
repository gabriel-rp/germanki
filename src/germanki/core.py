import base64
import os
import tempfile
from pathlib import Path
from random import randint
from typing import List, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field

import germanki
from germanki.anki_connect import (
    AnkiCard,
    AnkiConnectClient,
    AnkiConnectResponseError,
    AnkiMedia,
    AnkiMediaType,
)
from germanki.config import Config
from germanki.photos import PhotosClient, SearchResponse
from germanki.photos.exceptions import PhotosNotFoundError
from germanki.tts_mp3 import TTSAPI
from germanki.utils import get_logger

logger = get_logger(__file__)


class MediaUpdateException(Exception):
    query: str
    media_type: str
    exception: Exception

    def __init__(self, query: str, media_type: str, exception: Exception):
        self.query = query
        self.media_type = media_type
        self.exception = exception


class ImageUpdateException(Exception):
    query_words: List[str]
    exceptions: List[Exception]

    def __init__(self, query_words: str, exceptions: List[Exception]):
        self.query_words = query_words
        self.exceptions = exceptions


class MediaUpdateExceptions(Exception):
    exceptions: List[MediaUpdateException]

    def __init__(self, exceptions):
        self.exceptions = exceptions


class AnkiCardInfo(BaseModel):
    # front
    word: str
    # back
    translations: List[str]
    # extra
    definition: str
    examples: List[str]
    extra: str
    image_query_words: Optional[List[str]] = Field(default=None)
    translation_image_url: Optional[str] = Field(default=None)
    word_audio_url: Optional[str] = Field(default=None)
    speaker: str = Field(default='Vicki')

    @property
    def query_words(self) -> List[str]:
        return (
            self.image_query_words
            if self.image_query_words
            else self.translations
        )


class AnkiCardHTMLPreview(AnkiCard):
    front: str
    back: str
    extra: str


class CreateCardResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    card_word: str
    exception: Optional[AnkiConnectResponseError] = None


class AnkiCardCreator:
    @staticmethod
    def front(
        card_contents: AnkiCardInfo,
        audio: AnkiMedia,
        autoplay: bool = True,
        style: str = '',
    ) -> str:
        autoplay_controls = 'autoplay' if autoplay else ''
        b64_audio = Path(audio.path).read_text()
        return f'{card_contents.word}<br>' + (
            f'<audio controls {autoplay_controls} style="{style}">'
            f'<source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">'
            '</audio>'
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
        return ', '.join(card_contents.translations) + (
            f'<br><img src="{path}" style="{style}">' if image else ''
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
            )
            if card_contents.word_audio_url
            else None
        )
        image = (
            AnkiMedia(
                anki_media_type=AnkiMediaType.IMAGE,
                path=card_contents.translation_image_url,
            )
            if card_contents.translation_image_url
            else None
        )
        image_filename = image.filename if image else None
        media = []
        if image:
            media.append(image)
        if audio:
            media.append(audio)
        return AnkiCard(
            front=AnkiCardCreator.front(card_contents, audio),
            back=AnkiCardCreator.back(
                card_contents, image, image_filename, style='max-width: 500px;'
            ),
            extra=AnkiCardCreator.extra(card_contents),
            media=media,
        )

    @staticmethod
    def html_preview(card_contents: AnkiCardInfo) -> AnkiCardHTMLPreview:
        audio = None
        image = None
        image_path = None
        host = os.getenv('STREAMLIT_SERVER_ADDRESS', 'localhost')
        port = os.getenv('STREAMLIT_SERVER_PORT', '8501')

        if card_contents.word_audio_url:
            audio = AnkiMedia(
                anki_media_type=AnkiMediaType.AUDIO,
                path=card_contents.word_audio_url,
            )
        if card_contents.translation_image_url:
            image = AnkiMedia(
                anki_media_type=AnkiMediaType.IMAGE,
                path=card_contents.translation_image_url,
            )
            image_path = f'http://{host}:{port}/app/{image.path.relative_to(Path(germanki.__file__).parent)}'
        return AnkiCardHTMLPreview(
            front=AnkiCardCreator.front(
                card_contents,
                audio,
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

    def __init__(
        self,
        photos_client: PhotosClient,
        config: Config = Config(),
    ):
        self.photos_client = photos_client
        self.config = config
        self.selected_speaker = self.default_speaker
        self._card_contents = []

    @property
    def card_contents(self) -> List[AnkiCardInfo]:
        return self._card_contents

    @card_contents.setter
    def card_contents(self, card_contents: List[AnkiCardInfo]):
        self._card_contents = card_contents

        logger.info(f'Updating media for {len(self._card_contents)} cards')
        exceptions = []
        for index in range(len(card_contents)):
            try:
                self.update_card_image(index)
            except MediaUpdateException as e:
                exceptions.append(e)
                logger.info(
                    f'Card image update with query {e.query} failed. Exception: {e.exception}'
                )

            try:
                self.update_card_audio(index)
            except MediaUpdateException as e:
                exceptions.append(e)
                logger.info(
                    f'Card audio update with query {e.query} failed. Exception: {e.exception}'
                )

        if len(exceptions) > 0:
            logger.info(f'Media update raised {len(exceptions)} exceptions')
            raise MediaUpdateExceptions(exceptions=exceptions)

        logger.info(
            f'Media successfully updated for {len(self._card_contents)} cards'
        )

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

    def update_card_image(self, index: int) -> None:
        card = self._card_contents[index]
        exceptions = []

        for i, query_word in enumerate(card.query_words):
            try:
                card.translation_image_url = self._get_image(query_word)
                logger.debug(
                    f'Card image successfully updated with query {query_word}'
                )
                return
            except Exception as e:
                logger.debug(
                    f'Could not update card image with query {query_word}. Error: {e}'
                )
                if i != len(card.query_words) - 1:
                    # not last element
                    exceptions.append(e)

        raise ImageUpdateException(
            query_words=card.query_words, exceptions=exceptions
        )

    def update_card_audio(self, index: int) -> None:
        card = self._card_contents[index]
        try:
            card.word_audio_url = self._get_tts_audio(card.word)
        except Exception as e:
            logger.debug(
                f'Could not update card audio with query {card.word}. Error: {e}'
            )
            raise MediaUpdateException(
                query=card.word, media_type='audio', exception=e
            )

    def create_cards(self, deck_name: str) -> List[CreateCardResponse]:
        responses = []
        anki_client = AnkiConnectClient()
        for card_contents in self._card_contents:
            card = AnkiCardCreator.create(card_contents)
            response = CreateCardResponse(card_word=card_contents.word)
            try:
                self._create_card(
                    deck_name=deck_name,
                    anki_client=anki_client,
                    anki_card=card,
                )
            except AnkiConnectResponseError as e:
                response.exception = e

            responses.append(response)
        return responses

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
            logger.debug(f'image already exists: {image_path}')
            return image_path
        try:
            logger.debug(f'searching image with query {query}, page {page}')
            search_response: SearchResponse = (
                self.photos_client.search_random_photo(
                    query=query,
                    per_page=1,
                    page=page,
                )
            )
            if search_response.total_results == 0:
                raise
        except (PhotosNotFoundError):
            if page > int(page / 2):
                return self._get_image(query=query, max_pages=int(page / 2))
            if page == 1:
                raise

        response = requests.get(search_response.photo_urls[0])

        if response.status_code != 200 or not response.content:
            raise Exception(f'Error downloading image: {response.status_code}')

        with open(image_path, 'wb') as file:
            file.write(response.content)

        return image_path

    def _get_tts_audio(self, query: str) -> Optional[Path]:
        base_filename = f'{query}_{self.selected_speaker}'
        audio_path = self.config.audio_filepath(
            Germanki.convert_query_to_filename(base_filename, ext='mp3')
        )
        if audio_path.exists():
            return audio_path
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_file = Path(tmp_dir, base_filename)
                MP3Downloader.download_mp3(
                    msg=query, lang=self.selected_speaker, file_path=tmp_file
                )
                b64_audio = base64.b64encode(tmp_file.read_bytes()).decode()
                audio_path.write_text(b64_audio)
                return audio_path
        except Exception as e:
            raise e

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
