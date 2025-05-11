import os
from enum import Enum
from pathlib import Path
from typing import List

from pydantic.dataclasses import Field, dataclass

from germanki.static import audio, image


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


@dataclass
class Config:
    pexels_api_key: str = Field(
        default=os.environ.get('PEXELS_API_KEY', ''),
        description='Pexels API key necessary to search and download images',
    )
    unsplash_api_key: str = Field(
        default=os.environ.get('UNSPLASH_API_KEY', ''),
        description='Unsplash API key necessary to search and download images',
    )
    openai_api_key: str = Field(
        default=os.environ.get('OPENAI_API_KEY', ''),
        description='OpenAI API key necessary to generate card contents using ChatGPT',
    )
    audio_downloads_folder: Path = Field(default=Path(audio.__file__).parent)
    image_downloads_folder: Path = Field(default=Path(image.__file__).parent)
    enable_extra: bool = Field(default=True)
    image_position: ImagePosition = Field(default=ImagePosition.BACK)
    audio_position: AudioPosition = Field(default=AudioPosition.FRONT)
    speakers: List[TTSSpeaker] = Field(default=list(TTSSpeaker))
    default_speaker: TTSSpeaker = Field(default=TTSSpeaker.VICKI)

    def audio_filepath(self, filename: str) -> Path:
        return self.audio_downloads_folder / filename

    def image_filepath(self, filename: str) -> Path:
        return self.image_downloads_folder / filename
