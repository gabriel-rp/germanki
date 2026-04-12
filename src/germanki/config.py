import os
from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from platformdirs import user_data_dir

from germanki.static import audio, image

# Standard location for germanki data:
# macOS: ~/Library/Application Support/germanki
# Linux: ~/.local/share/germanki
# Windows: C:\Users\<user>\AppData\Local\germanki\germanki
DATA_DIR = Path(user_data_dir("germanki"))


class ImagePosition(Enum):
    BACK = 'back'
    FRONT = 'front'
    BOTH = 'both'
    NONE = 'none'


class AudioPosition(Enum):
    BACK = 'back'
    FRONT = 'front'
    BOTH = 'both'
    NONE = 'none'


class TTSSpeaker(Enum):
    VICKI = 'Vicki'
    MARLENE = 'Marlene'
    HANS = 'Hans'


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', extra='ignore'
    )

    pexels_api_key: str = Field(
        default='',
        description='Pexels API key necessary to search and download images',
    )
    unsplash_api_key: str = Field(
        default='',
        description='Unsplash API key necessary to search and download images',
    )
    openai_api_key: str = Field(
        default='',
        description='OpenAI API key necessary to generate card contents using ChatGPT',
    )
    audio_downloads_folder: Path = Field(default=DATA_DIR / "media" / "audio")
    image_downloads_folder: Path = Field(default=DATA_DIR / "media" / "image")
    db_path: Path = Field(default=DATA_DIR / "germanki.db")

    enable_extra: bool = Field(default=True)
    image_position: ImagePosition = Field(default=ImagePosition.BACK)
    audio_position: AudioPosition = Field(default=AudioPosition.FRONT)
    speakers: list[TTSSpeaker] = Field(default=list(TTSSpeaker))
    default_speaker: TTSSpeaker = Field(default=TTSSpeaker.VICKI)

    def __init__(self, **values):
        super().__init__(**values)
        # Ensure directories exist
        self.audio_downloads_folder.mkdir(parents=True, exist_ok=True)
        self.image_downloads_folder.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def audio_filepath(self, filename: str) -> Path:
        return self.audio_downloads_folder / filename

    def image_filepath(self, filename: str) -> Path:
        return self.image_downloads_folder / filename
