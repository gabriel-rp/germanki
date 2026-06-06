import json
from pathlib import Path
from uuid import uuid4
from typing import Dict
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from germanki.config import Config
from germanki.core import AnkiCardInfo


class UserSession(BaseModel):
    session_id: str
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cards: list[AnkiCardInfo] = []
    deck_name: str = 'Germanki Deck'
    selected_speaker: str = 'Vicki'
    input_source: str = 'chatgpt'
    input_text: str = ''
    llm_model: str = 'gpt-4o-mini'
    photo_source: str = 'pexels'
    enable_images: bool = True
    pexels_api_key: str | None = None
    unsplash_api_key: str | None = None
    openai_api_key: str | None = None


class SessionManager:
    _sessions: Dict[str, UserSession] = {}

    @classmethod
    async def initialize(cls):
        # No longer needed for SQLite, but keeping for compatibility
        pass

    @classmethod
    async def get_session(cls, session_id: str) -> UserSession:
        if session_id in cls._sessions:
            session = cls._sessions[session_id]
            session.last_accessed = datetime.now(timezone.utc)
            return session
        
        # If not found, return a new one but don't save yet
        return UserSession(session_id=session_id)

    @classmethod
    async def save_session(cls, session: UserSession):
        session.last_accessed = datetime.now(timezone.utc)
        cls._sessions[session.session_id] = session

    @classmethod
    async def create_session(cls) -> str:
        session_id = str(uuid4())
        session = UserSession(session_id=session_id)
        await cls.save_session(session)
        return session_id

    @classmethod
    async def delete_session(cls, session_id: str):
        if session_id in cls._sessions:
            del cls._sessions[session_id]

    @classmethod
    def list_sessions(cls) -> Dict[str, UserSession]:
        return cls._sessions
