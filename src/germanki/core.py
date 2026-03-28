import base64
import os
import tempfile
import asyncio
from pathlib import Path
from random import randint

import httpx
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
    query_words: list[str]
    exceptions: list[Exception]

    def __init__(self, query_words: list[str], exceptions: list[Exception]):
        self.query_words = query_words
        self.exceptions = exceptions


class MediaUpdateExceptions(Exception):
    exceptions: list[MediaUpdateException]

    def __init__(self, exceptions):
        self.exceptions = exceptions


class AnkiCardInfo(BaseModel):
    # front
    word: str
    # back
    translations: list[str]
    # extra
    definition: str
    examples: list[str]
    extra: str
    image_query_words: list[str] | None = Field(default=None)
    translation_image_url: str | None = Field(default=None)
    word_audio_url: str | None = Field(default=None)
    speaker: str = Field(default='Vicki')

    @property
    def query_words(self) -> list[str]:
        return (
            self.image_query_words
            if self.image_query_words
            else self.translations
        )


class CreateCardResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    card_word: str
    exception: AnkiConnectResponseError | None = None


class AnkiCardCreator:
    @staticmethod
    def front(
        env,
        card_contents: AnkiCardInfo,
        audio: AnkiMedia | None,
    ) -> str:
        audio_base64 = None
        if audio:
            audio_base64 = base64.b64encode(Path(audio.path).read_bytes()).decode()
        
        template = env.get_template("anki/front.html")
        return template.render(card=card_contents, audio=audio, audio_base64=audio_base64)

    @staticmethod
    def back(
        env,
        card_contents: AnkiCardInfo,
        image: AnkiMedia | None,
        style: str = '',
    ) -> str:
        image_filename = image.filename if image else None
        template = env.get_template("anki/back.html")
        return template.render(card=card_contents, image=image, image_filename=image_filename, style=style)

    @staticmethod
    def extra(env, card_contents: AnkiCardInfo) -> str:
        template = env.get_template("anki/extra.html")
        return template.render(card=card_contents)

    @staticmethod
    def create(env, card_contents: AnkiCardInfo) -> AnkiCard:
        audio = (
            AnkiMedia(
                anki_media_type=AnkiMediaType.AUDIO,
                path=Path(card_contents.word_audio_url),
            )
            if card_contents.word_audio_url
            else None
        )
        image = (
            AnkiMedia(
                anki_media_type=AnkiMediaType.IMAGE,
                path=Path(card_contents.translation_image_url),
            )
            if card_contents.translation_image_url
            else None
        )
        
        media = []
        if image:
            media.append(image)
        if audio:
            media.append(audio)
            
        return AnkiCard(
            front=AnkiCardCreator.front(env, card_contents, audio),
            back=AnkiCardCreator.back(
                env, card_contents, image, style='max-width: 500px;'
            ),
            extra=AnkiCardCreator.extra(env, card_contents),
            media=media,
        )


class MP3Downloader:
    @staticmethod
    async def download_mp3(msg: str, lang: str, file_path: Path) -> None:
        tts_api = TTSAPI()
        tts_response = await tts_api.request_tts(msg=msg, lang=lang)
        if tts_response.success:
            if await tts_api.download_mp3(
                mp3_url=tts_response.mp3_url, file_path=file_path
            ):
                pass
            else:
                raise Exception("Failed to download MP3")
        else:
            raise Exception(f"TTS request failed: {tts_response.error_message}")


class Germanki:
    _selected_speaker: str

    def __init__(
        self,
        photos_client: PhotosClient,
        config: Config = Config(),
    ):
        self.photos_client = photos_client
        self.config = config
        self.selected_speaker = self.default_speaker

    async def populate_media(self, cards: list[AnkiCardInfo], skip_images: bool = False) -> list[Exception]:
        logger.info(f'Updating media for {len(cards)} cards in parallel')
        tasks = []
        for card in cards:
            if not skip_images:
                tasks.append(self.update_card_image(card))
            tasks.append(self.update_card_audio(card))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.warning(f'Media update encountered {len(exceptions)} exceptions')
            for e in exceptions:
                logger.error(f"Media update error: {e}")

        logger.info(f'Media successfully updated for {len(cards)} cards')
        return exceptions

    @property
    def speakers(self) -> list[str]:
        return [speaker.value for speaker in self.config.speakers]

    @property
    def default_speaker(self) -> str:
        return str(self.config.default_speaker.value)

    @property
    def selected_speaker(self) -> str:
        return self._selected_speaker

    @selected_speaker.setter
    def selected_speaker(self, speaker: str):
        if speaker not in self.speakers:
            raise ValueError('Invalid speaker.')
        self._selected_speaker = speaker

    async def update_card_image(self, card: AnkiCardInfo) -> None:
        exceptions = []

        for i, query_word in enumerate(card.query_words):
            try:
                card.translation_image_url = str(await self._get_image(query_word))
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

    async def update_card_audio(self, card: AnkiCardInfo) -> None:
        try:
            card.word_audio_url = str(await self._get_tts_audio(card.word))
        except Exception as e:
            logger.debug(
                f'Could not update card audio with query {card.word}. Error: {e}'
            )
            raise MediaUpdateException(
                query=card.word, media_type='audio', exception=e
            )

    async def create_cards(self, env, cards: list[AnkiCardInfo], deck_name: str, force_update: bool = False) -> list[CreateCardResponse]:
        responses = []
        anki_client = AnkiConnectClient()
        
        # Ensure germanki_card model exists and is up to date
        try:
            await self._ensure_germanki_model(anki_client, force_update=force_update)
        except Exception as e:
            logger.error(f"Failed to ensure germanki_card model: {e}")

        for card_contents in cards:
            card = AnkiCardCreator.create(env, card_contents)
            response = CreateCardResponse(card_word=card_contents.word)
            try:
                await self._create_card(
                    deck_name=deck_name,
                    anki_client=anki_client,
                    anki_card=card,
                )
            except AnkiConnectResponseError as e:
                response.exception = e

            responses.append(response)
        return responses

    async def check_model_outdated(self, anki_client: AnkiConnectClient) -> bool:
        model_name = "germanki_card"
        models = await anki_client.get_model_names()
        if model_name not in models:
            return False # It doesn't exist, so it will be created normally
        
        info = await anki_client.get_model_info(model_name)
        if not info:
            return False

        # Check CSS
        expected_css = ".card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }"
        if info.get("css", "").strip() != expected_css.strip():
            return True

        # Check Templates
        expected_templates = {
            "Forward (Front -> Back)": {
                "Front": "{{Front}}",
                "Back": "{{FrontSide}}\n\n<hr id=answer>\n\n\n{{#Extra}}\n    {{Extra}}\n{{/Extra}}\n<br><br>\n{{Back}}",
            },
            "Backward (Back -> Front)": {
                "Front": "{{Back}}",
                "Back": "{{FrontSide}}\n\n<hr id=answer>\n\n{{Front}}\n\n<br><br>\n{{#Extra}}\n    {{Extra}}\n{{/Extra}}",
            },
        }

        existing_templates = info.get("tmpls", [])
        if len(existing_templates) != len(expected_templates):
            return True

        for tmpl in existing_templates:
            name = tmpl.get("name")
            if name not in expected_templates:
                return True
            
            expected = expected_templates[name]
            # Normalize whitespace for comparison
            if tmpl.get("qfmt", "").strip() != expected["Front"].strip():
                return True
            if tmpl.get("afmt", "").strip() != expected["Back"].strip():
                return True
                
        return False

    async def _ensure_germanki_model(self, anki_client: AnkiConnectClient, force_update: bool = False):
        model_name = "germanki_card"
        in_order_fields = ["Front", "Back", "Extra"]
        card_templates = [
            {
                "Name": "Forward (Front -> Back)",
                "Front": "{{Front}}",
                "Back": "{{FrontSide}}\n\n<hr id=answer>\n\n\n{{#Extra}}\n    {{Extra}}\n{{/Extra}}\n<br><br>\n{{Back}}",
            },
            {
                "Name": "Backward (Back -> Front)",
                "Front": "{{Back}}",
                "Back": "{{FrontSide}}\n\n<hr id=answer>\n\n{{Front}}\n\n<br><br>\n{{#Extra}}\n    {{Extra}}\n{{/Extra}}",
            },
        ]
        css = ".card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }"

        models = await anki_client.get_model_names()
        if model_name not in models:
            logger.info(f"Creating model {model_name} in Anki")
            await anki_client.create_model(
                model_name=model_name,
                in_order_fields=in_order_fields,
                card_templates=card_templates,
                css=css,
            )
        elif force_update:
            logger.info(f"Forced update of model {model_name} templates and styling in Anki")
            # Update templates
            templates_dict = {
                t["Name"]: {"Front": t["Front"], "Back": t["Back"]}
                for t in card_templates
            }
            await anki_client.update_model_templates(model_name, templates_dict)
            # Update styling
            await anki_client.update_model_styling(model_name, css)

    async def _create_card(
        self,
        deck_name: str,
        anki_client: AnkiConnectClient,
        anki_card: AnkiCard,
    ):
        await anki_client.add_card(
            deck_name=deck_name,
            anki_card=anki_card,
            model="germanki_card",
        )

    async def _get_image(self, query: str, max_pages: int = 100) -> Path | None:
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
                await self.photos_client.search_random_photo(
                    query=query,
                    per_page=1,
                    page=page,
                )
            )
            if search_response.total_results == 0:
                raise PhotosNotFoundError(f"No results for {query}")
        except (PhotosNotFoundError):
            if page > int(page / 2):
                return await self._get_image(query=query, max_pages=int(page / 2))
            if page == 1:
                raise

        async with httpx.AsyncClient() as client:
            response = await client.get(search_response.photo_urls[0])

            if response.status_code != 200 or not response.content:
                raise Exception(f'Error downloading image: {response.status_code}')

            image_path.write_bytes(response.content)

        return image_path

    async def _get_tts_audio(self, query: str) -> Path | None:
        base_filename = f'{query}_{self.selected_speaker}'
        audio_path = self.config.audio_filepath(
            Germanki.convert_query_to_filename(base_filename, ext='mp3')
        )
        if audio_path.exists():
            return audio_path
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_file = Path(tmp_dir, base_filename)
                await MP3Downloader.download_mp3(
                    msg=query, lang=self.selected_speaker, file_path=tmp_file
                )
                audio_path.write_bytes(tmp_file.read_bytes())
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
