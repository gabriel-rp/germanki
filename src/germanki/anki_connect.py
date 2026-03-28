import base64
import asyncio
import httpx

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


class AnkiMediaType(Enum):
    IMAGE = "image"
    AUDIO = "audio"


class AnkiMedia(BaseModel):
    path: Path
    anki_media_type: AnkiMediaType

    @property
    def filename(self) -> str:
        return self.path.name


class AnkiCard(BaseModel):
    front: str
    back: str
    extra: str = Field(default="")
    media: list[AnkiMedia] = Field(default=[])


class AnkiConnectError(Exception):
    """Base exception for AnkiConnect errors."""

    pass


class AnkiConnectRequestError(AnkiConnectError):
    """Exception raised for request failures (e.g., connection issues)."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(f"Request failed: {message} (Status Code: {status_code})")


class AnkiConnectResponseError(AnkiConnectError):
    """Exception raised when AnkiConnect returns an error response."""

    def __init__(self, action: str, error: str):
        super().__init__(f"AnkiConnect error on action '{action}': {error}")


class AnkiConnectDeckNotExistsError(AnkiConnectError):
    def __init__(self, deck_name: str):
        self.deck_name = deck_name
        super().__init__(f"Deck '{deck_name}' does not exist.")


class AnkiConnectClient:
    """Client for interacting with the AnkiConnect API asynchronously."""

    def __init__(
        self,
        host: str = "http://localhost",
        port: int = 8765,
        version: int = 6,
        timeout: int = 5,
        default_tags: list[str] | None = None,
    ):
        self.base_url = f"{host}:{port}"
        self.version = version
        self.timeout = timeout
        self.default_tags = (
            default_tags
            if default_tags
            else [
                "automated",
                datetime.now().strftime("%Y-%m-%d"),
            ]
        )

    async def _request(
        self, action: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Internal method to send an asynchronous request to AnkiConnect."""
        payload = {
            "action": action,
            "version": self.version,
            "params": params or {},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise AnkiConnectRequestError(
                str(e),
                getattr(e.response, "status_code", None)
                if hasattr(e, "response")
                else None,
            )

        data = response.json()

        if "error" in data and data["error"]:
            raise AnkiConnectResponseError(action, data["error"])

        return data.get("result")

    def _add_note_payload_params(
        self,
        deck_name: str,
        anki_card: AnkiCard,
        tags: list[str] | None,
        model: str,
        allow_duplicate: bool,
    ) -> dict[str, Any]:
        tags = tags if tags else []
        return {
            "deckName": deck_name,
            "modelName": model,
            "fields": {
                "Front": anki_card.front,
                "Back": anki_card.back,
                "Extra": anki_card.extra,
            },
            "tags": self.default_tags + tags,
            "options": {"allowDuplicate": allow_duplicate},
        }

    async def add_card(
        self,
        deck_name: str,
        anki_card: AnkiCard,
        tags: list[str] | None = None,
        model: str = "germanki_card",
        allow_duplicate: bool = False,
        create_deck_if_not_exists: bool = True,
    ) -> dict[str, Any]:
        """Adds one card asynchronously."""
        deck_exists = await self._deck_exists(deck_name)
        if not deck_exists:
            if not create_deck_if_not_exists:
                raise AnkiConnectDeckNotExistsError(deck_name=deck_name)
            await self._create_deck(deck_name)

        await self.upload_media_from_card(anki_card)

        return await self._request(
            "addNote",
            {
                "note": self._add_note_payload_params(
                    deck_name, anki_card, tags, model, allow_duplicate
                )
            },
        )

    async def _create_deck(self, deck_name: str) -> dict[str, Any]:
        return await self._request("createDeck", {"deck": deck_name})

    async def _deck_exists(self, deck_name: str) -> bool:
        decks = await self.get_deck_names()
        return decks is not None and deck_name in decks

    async def get_deck_names(self) -> list[str]:
        """Fetches the list of all deck names from Anki."""
        return await self._request("deckNames") or []

    async def get_model_names(self) -> list[str]:
        """Fetches the list of all model names from Anki."""
        return await self._request("modelNames") or []

    async def get_model_info(self, model_name: str) -> dict[str, Any]:
        """Fetches detailed information about a model (note type)."""
        return await self._request("modelInfo", {"modelName": model_name})

    async def create_model(
        self,
        model_name: str,
        in_order_fields: list[str],
        card_templates: list[dict[str, str]],
        css: str = "",
    ) -> dict[str, Any]:
        """Creates a new model (note type) in Anki."""
        params = {
            "modelName": model_name,
            "inOrderFields": in_order_fields,
            "cardTemplates": card_templates,
            "css": css,
        }
        return await self._request("createModel", params)

    async def update_model_templates(
        self,
        model_name: str,
        card_templates: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        """Updates model templates in Anki. card_templates is a dict where key is template name."""
        params = {
            "model": {
                "name": model_name,
                "templates": card_templates,
            }
        }
        return await self._request("updateModelTemplates", params)

    async def update_model_styling(
        self,
        model_name: str,
        css: str,
    ) -> dict[str, Any]:
        """Updates model styling in Anki."""
        params = {
            "model": {
                "name": model_name,
                "css": css,
            }
        }
        return await self._request("updateModelStyling", params)

    async def upload_media(self, anki_media: AnkiMedia) -> dict[str, Any]:
        """Uploads a media file (image or audio) to Anki asynchronously."""

        if not anki_media.path.exists():
            raise FileNotFoundError(f"File not found: {anki_media.path}")

        params = {
            "filename": anki_media.filename,
            "data": base64.b64encode(anki_media.path.read_bytes()).decode("utf-8"),
        }
        return await self._request("storeMediaFile", params)

    async def upload_media_from_card(self, anki_card: AnkiCard) -> list[dict[str, Any]]:
        return await asyncio.gather(
            *[self.upload_media(media) for media in anki_card.media]
        )
