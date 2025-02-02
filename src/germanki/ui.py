from enum import Enum
from pathlib import Path
from typing import List, Optional

import streamlit as st
import yaml
from pydantic import Field
from pydantic.dataclasses import dataclass

from germanki.core import Germanki
from germanki.data import input_examples


class RefreshOption(Enum):
    ALL = 'ALL'
    SELECTED = 'SELECTED'
    NO_REFRESH = 'NO_REFRESH'


@dataclass
class PreviewRefreshConfig:
    option: RefreshOption = Field(default=RefreshOption.ALL)
    selected_index: Optional[int] = None
    card_inputs: Optional[str] = None
    selected_speaker_input: Optional[str] = None

    def reset(self):
        self.option = RefreshOption.ALL
        self.selected_index = None


class UIController:
    preview_refresh_config: PreviewRefreshConfig
    _PAGE_HEIGHT = 500

    def __init__(self, preview_columns: int = 3):
        self._germanki = Germanki()
        self.preview_refresh_config = None
        self.preview_columns = preview_columns

    @staticmethod
    def default_input_text() -> str:
        return (
            Path(input_examples.__file__).parent / 'default.yaml'
        ).read_text()

    @property
    def page_height(self) -> int:
        return UIController._PAGE_HEIGHT

    @property
    def speakers(self) -> List[str]:
        return self._germanki.speakers

    @property
    def selected_speaker(self) -> List[str]:
        return self._germanki.selected_speaker

    def refresh_preview_action(self):
        if self.preview_refresh_config is not None:
            self.refresh_preview(self.preview_refresh_config)
            self.preview_refresh_config = None

    def preview_cards_action(
        self, cards_input: str, selected_speaker_input: str
    ):
        if len(cards_input) == 0:
            st.warning('Please provide card contents.')
            self.preview_refresh_config = PreviewRefreshConfig(
                RefreshOption.NO_REFRESH
            )
            return
        try:
            yaml.load(cards_input, Loader=yaml.FullLoader)
            self.preview_refresh_config = PreviewRefreshConfig(
                RefreshOption.ALL,
                card_inputs=cards_input,
                selected_speaker_input=selected_speaker_input,
            )
        except:
            st.warning('Invalid YAML input.')

    def create_cards_action(self, deck_name: str):
        try:
            self.create_cards(deck_name)
        except Exception as e:
            st.warning(f'Error while adding cards. {e}')

        self.preview_refresh_config = PreviewRefreshConfig(
            RefreshOption.NO_REFRESH
        )

    def update_germanki_cards(
        self, refresh_config: PreviewRefreshConfig
    ) -> None:
        if refresh_config.option == RefreshOption.NO_REFRESH:
            return

        if refresh_config.option == RefreshOption.SELECTED:
            self._germanki.refresh_card_images(refresh_config.selected_index)
            return

        if refresh_config.option == RefreshOption.ALL:
            self._germanki.selected_speaker = (
                refresh_config.selected_speaker_input
            )
            self._germanki.cards = refresh_config.card_inputs
            return

    def create_cards(self, deck_name: str):
        self._germanki.create_cards(deck_name)

    def refresh_preview(self, refresh_config: PreviewRefreshConfig):
        self.update_germanki_cards(refresh_config)
        preview_cols = st.columns(self.preview_columns)
        for index in range(len(self._germanki.cards)):
            with preview_cols[index % self.preview_columns]:
                self.draw_card(index)

    def draw_card(self, index: int):
        def set_selected_index() -> None:
            self.preview_refresh_config = PreviewRefreshConfig(
                option=RefreshOption.SELECTED, selected_index=index
            )

        def add_refresh_button(id: str) -> None:
            st.button(
                f'Refresh Image',
                icon='🔄',
                type='secondary',
                key=f'refresh_images_{index}_{id}',
                on_click=set_selected_index,
                use_container_width=True,
            )

        def add_image_if_exists(image_path: str, id: str) -> None:
            if image_path:
                st.image(image_path)
                add_refresh_button(id)

        def add_audio_if_exists(audio) -> None:
            if audio:
                st.audio(audio)

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
                f'<span>{part}</span>'
                for part in content.split('\n')
                if len(part.strip()) > 0
            )
            return f'<div style="background-color: rgba(51, 51, 51, 0.04); padding: 10px">{content_html}</div>'

        def write_section_divider(text: str) -> None:
            st.write(section_divider_html(text), unsafe_allow_html=True)

        def write_card_content(text: str) -> None:
            st.write(card_part_contents_html(text), unsafe_allow_html=True)

        # Start of UI refresh
        with st.expander(
            f'**Card {index+1} Preview**',
            icon='📄',
            expanded=True,
        ):
            write_section_divider('FRONT')
            write_card_content(self._germanki.cards[index].front)
            add_image_if_exists(
                self._germanki.cards[index].front_image, 'front'
            )
            add_audio_if_exists(self._germanki.cards[index].front_audio)

            write_section_divider('BACK')
            write_card_content(self._germanki.cards[index].back)
            add_image_if_exists(self._germanki.cards[index].back_image, 'back')
            add_audio_if_exists(self._germanki.cards[index].back_audio)

            write_section_divider('EXTRA')
            write_card_content(self._germanki.cards[index].extra)
