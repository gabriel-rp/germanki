from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import List, Optional

import streamlit as st
import yaml
from pydantic import Field
from pydantic.dataclasses import dataclass

from germanki.chatgpt import WEB_UI_CHATGPT_PROMPT, ChatGPTAPI
from germanki.config import Config
from germanki.core import (
    AnkiCardCreator,
    AnkiCardHTMLPreview,
    AnkiCardInfo,
    CreateCardResponse,
    Germanki,
    MediaUpdateExceptions,
)
from germanki.photos.pexels import PexelsClient
from germanki.photos.unsplash import UnsplashClient
from germanki.static import audio, input_examples
from germanki.utils import get_logger

logger = get_logger(__file__)


class RefreshOption(Enum):
    ALL = 'ALL'
    SELECTED = 'SELECTED'
    NO_REFRESH = 'NO_REFRESH'


class InputSource(Enum):
    CHATGPT = 'ChatGPT'
    MANUAL = 'Manual'

    @staticmethod
    def from_str(input_source_text: str) -> 'InputSource':
        for item in list(InputSource):
            if item.value == input_source_text:
                return item
        raise ValueError('Invalid input source')


class PhotoSource(Enum):
    PEXELS = 'Pexels'
    UNSPLASH = 'Unsplash'

    @staticmethod
    def from_str(photo_source_text: str) -> 'PhotoSource':
        for item in list(PhotoSource):
            if item.value == photo_source_text:
                return item
        raise ValueError(f'Invalid photo source "{photo_source_text}"')


@dataclass
class PreviewRefreshConfig:
    option: RefreshOption = Field(default=RefreshOption.NO_REFRESH)
    selected_index: Optional[int] = None


class InputSourceHandlerException(Exception):
    pass


class InvalidManualInputException(InputSourceHandlerException):
    pass


class OpenAPIKeyNotProvided(InputSourceHandlerException):
    pass


class InputSourceUIHandler(ABC):
    @abstractmethod
    def parse(self, input_text: str) -> List[AnkiCardInfo]:
        raise NotImplementedError()

    @abstractmethod
    def create_input_field(self, window_height: int):
        raise NotImplementedError()


class ChatGPTUIHandler(InputSourceUIHandler):
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        if not self.openai_api_key:
            raise OpenAPIKeyNotProvided('OpenAI API key not provided')
        self.chatgpt_api = ChatGPTAPI(openai_api_key)

    def parse(self, input_text: str) -> List[AnkiCardInfo]:
        logger.info(
            f'Parsing {len(input_text.splitlines())}-line input with ChatGPT'
        )
        card_content_collection = self.chatgpt_api.query(input_text)
        logger.info(f'Successfully parsed input with ChatGPT')
        return card_content_collection.card_contents

    def create_input_field(self, window_height: int):
        with st.expander('ChatGPT Input', expanded=True):
            return st.text_area(
                'Enter your words/expressions, one in each line, and ChatGPT will generate the cards for you.',
                value='Hund\nMann\nFrau',
                height=window_height,
            )


class ManualInputUIHandler(InputSourceUIHandler):
    def parse(self, input_text: str) -> List[AnkiCardInfo]:
        if len(input_text) == 0:
            raise InvalidManualInputException('No input provided.')

        try:
            cards_list = yaml.load(input_text, Loader=yaml.Loader)
        except:
            raise InvalidManualInputException('Invalid YAML input.')

        return [AnkiCardInfo(**card_content) for card_content in cards_list]

    def _default_manual_input(self) -> str:
        return (
            Path(input_examples.__file__).parent / 'default.yaml'
        ).read_text()

    def create_input_field(self, window_height: int):
        with st.expander(
            'Use this ChatGPT prompt for the free web version',
            expanded=False,
            icon='⚠️',
        ):
            st.markdown(
                'Go to [ChatGPT](https://chatgpt.com/), and paste the prompt below.\n'
                'Give it the words you want to create cards for afterwards.'
            )
            st.markdown(f'```\n{WEB_UI_CHATGPT_PROMPT}\n```')
        with st.expander('Manual Input', expanded=True):
            return st.text_area(
                'YAML-formatted list with fields `word`, `translations`, `extra`, `definition`, `examples`, `image_query_words`',
                value=self._default_manual_input(),
                height=window_height,
            )


class UIController:
    _germanki: Germanki
    _refresh_config: PreviewRefreshConfig
    _input_source: InputSource
    ui_handler: InputSourceUIHandler
    preview_columns: int
    fallback_input_source: InputSource
    _photo_source: PhotoSource

    def __init__(
        self,
        default_input_source: InputSource,
        preview_columns: int = 3,
        fallback_input_source: InputSource = InputSource.MANUAL,
        default_photo_source: PhotoSource = PhotoSource.PEXELS,
    ):
        config = Config()
        self._germanki = Germanki(
            PexelsClient(config.pexels_api_key), config=config
        )
        self.preview_columns = preview_columns
        try:
            self.input_source = default_input_source
        except:
            self.input_source = fallback_input_source
        self._photo_source = default_photo_source

        # ensures nothing is refreshed at first
        self._refresh_config = self._refresh_nothing_config()

    @property
    def input_source(self) -> InputSource:
        st.warning(f'input_source {self._input_source}')
        return self._input_source

    @input_source.setter
    def input_source(self, input_source: InputSource):
        if input_source == InputSource.CHATGPT:
            try:
                self.ui_handler = ChatGPTUIHandler(
                    self._germanki.config.openai_api_key
                )
            except OpenAPIKeyNotProvided:
                raise OpenAPIKeyNotProvided(
                    "OpenAI API key not provided. Can't use ChatGPT input mode."
                )
        elif input_source == InputSource.MANUAL:
            self.ui_handler = ManualInputUIHandler()
        else:
            st.warning(f'Invalid input source {input_source}.\n')

        self._input_source = input_source

    @property
    def photo_source(self) -> PhotoSource:
        return self._photo_source

    @photo_source.setter
    def photo_source(self, photo_source: PhotoSource):
        if photo_source == PhotoSource.PEXELS:
            if not self._germanki.config.pexels_api_key:
                st.warning('Pexels API key not provided.')
                return
            self._germanki.photos_client = PexelsClient(
                self._germanki.config.pexels_api_key
            )
        if photo_source == PhotoSource.UNSPLASH:
            if not self._germanki.config.unsplash_api_key:
                st.warning('Unsplash API key not provided.')
                return
            self._germanki.photos_client = UnsplashClient(
                self._germanki.config.unsplash_api_key
            )
        if photo_source not in list(PhotoSource):
            st.warning(f'Invalid photo source {photo_source}.')

        self._photo_source = photo_source

    @property
    def default_window_height(self) -> int:
        return 400

    @property
    def speakers(self) -> List[str]:
        return self._germanki.speakers

    @property
    def selected_speaker(self) -> str:
        return self._germanki.selected_speaker

    def _refresh_all_config(self) -> PreviewRefreshConfig:
        return PreviewRefreshConfig(RefreshOption.ALL)

    def _refresh_nothing_config(self) -> PreviewRefreshConfig:
        return PreviewRefreshConfig(RefreshOption.NO_REFRESH)

    def create_input_field(self):
        return self.ui_handler.create_input_field(self.default_window_height)

    def update_api_keys_action(
        self, pexels_api_key: str, openai_api_key: str, unsplash_api_key: str
    ) -> None:
        if pexels_api_key:
            self._germanki.config.pexels_api_key = pexels_api_key
        if openai_api_key:
            self._germanki.config.openai_api_key = openai_api_key
        if unsplash_api_key:
            self._germanki.config.unsplash_api_key = unsplash_api_key

    def select_speaker_action(self, selected_speaker_input: str) -> None:
        # TODO: play sample audio
        try:
            self._germanki.selected_speaker = selected_speaker_input
        except ValueError:
            st.warning('Invalid speaker.')
            raise
        sample_audio_path = (
            Path(audio.__file__).parent
            / f'sample_{selected_speaker_input}.mp3'
        )
        if sample_audio_path.exists():
            st.write('Sample audio:')
            st.audio(sample_audio_path.read_bytes(), format='audio/mpeg')

    def preview_cards_action(self, cards_input: str) -> None:
        try:
            st.info('Parsing Input...')
            card_contents = self.ui_handler.parse(cards_input)
            st.info('Generating Preview...')
            self._germanki.card_contents = card_contents
        except (InvalidManualInputException, InvalidManualInputException) as e:
            st.warning(f'Please provide valid card contents. Error: {e}')
        except MediaUpdateExceptions as e:
            st.warning(f'Could not update card media. Errors: {e.exceptions}')

        self._refresh_config = PreviewRefreshConfig(RefreshOption.ALL)

    def create_cards_action(self, deck_name: str):
        try:
            responses: List[CreateCardResponse] = self.create_cards(deck_name)
            for response in responses:
                if not response.exception:
                    continue

                st.warning(
                    f"Error while adding card '{response.card_word}'. {response.exception}"
                )

        except Exception as e:
            st.warning(f'Error while adding cards. {e}')
            raise
        self._refresh_nothing_config()

    def create_cards(self, deck_name: str) -> List[CreateCardResponse]:
        return self._germanki.create_cards(deck_name)

    def refresh_preview(self):
        preview_cols = st.columns(self.preview_columns)
        for index in range(len(self._germanki.card_contents)):
            with preview_cols[index % self.preview_columns]:
                self.draw_card(index)

    def draw_card(self, index: int):
        card: AnkiCardHTMLPreview = AnkiCardCreator.html_preview(
            self._germanki.card_contents[index]
        )

        def set_selected_index() -> None:
            self.status_bar = 'Refreshing image...'
            logger.info(
                f'Requested image refresh for card {self._germanki.card_contents[index].word}'
            )
            try:
                self._germanki.update_card_image(index)
            except Exception as e:
                st.warning(f'Could not add media to card. Error: {e}')
            self.status_bar = ''

        def add_refresh_button() -> None:
            st.button(
                f'Refresh Image (search terms: {self._germanki.card_contents[index].query_words})',
                icon='🔄',
                type='secondary',
                key=f'refresh_images_{index}',
                on_click=set_selected_index,
                use_container_width=True,
            )

        def section_divider_html(title: str) -> str:
            border_style = 'border-style: solid; border-width: 1px 1px 2px 1px; border-color: #f7d1d1; border-radius: 2px;'
            div_style = f'width: 100%; text-align: center; background-color: #ffffff52; margin: 10px 0 5px; {border_style}'
            text_style = 'font-size: 13px; color: rgb(255, 111, 97);'
            return (
                f'<div style="{div_style}"><span style="{text_style}">'
                f'{title}'
                '</span></div>'
            )

        def card_part_contents_html(content: str) -> str:
            content_html = ''.join(
                f'<span>{part}</span><br>'
                for part in content.split('\n')
                if len(part.strip()) > 0
            )
            return f'<div style="background-color: rgba(51, 51, 51, 0.04); padding: 10px">{content_html}</div>'

        def write_section_divider(text: str) -> None:
            st.write(section_divider_html(text), unsafe_allow_html=True)

        def write_card_content(text: str) -> None:
            st.markdown(card_part_contents_html(text), unsafe_allow_html=True)

        # Start of UI refresh
        with st.expander(
            f'**Card {index+1}**',
            icon='📄',
            expanded=True,
        ):
            add_refresh_button()
            write_section_divider('FRONT')
            write_card_content(card.front)

            write_section_divider('BACK')
            write_card_content(card.back)

            write_section_divider('EXTRA')
            write_card_content(card.extra)
