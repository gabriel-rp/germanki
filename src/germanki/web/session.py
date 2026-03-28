import json
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel

from germanki.config import Config
from germanki.core import AnkiCardInfo


class UserSession(BaseModel):
    session_id: str
    cards: list[AnkiCardInfo] = []
    deck_name: str = 'Germanki Deck'
    selected_speaker: str = 'Vicki'
    input_source: str = 'chatgpt'
    photo_source: str = 'pexels'
    enable_images: bool = True
    pexels_api_key: str | None = None
    unsplash_api_key: str | None = None
    openai_api_key: str | None = None


class SessionManager:
    _db_path = Config().db_path

    @classmethod
    async def initialize(cls):
        async with aiosqlite.connect(cls._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT
                )
            """
            )
            await db.commit()

    @classmethod
    async def get_session(cls, session_id: str) -> UserSession:
        async with aiosqlite.connect(cls._db_path) as db:
            async with db.execute(
                'SELECT data FROM sessions WHERE session_id = ?', (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return UserSession(**json.loads(row[0]))

        # If not found, return a new one but don't save yet
        return UserSession(session_id=session_id)

    @classmethod
    async def save_session(cls, session: UserSession):
        async with aiosqlite.connect(cls._db_path) as db:
            await db.execute(
                'INSERT OR REPLACE INTO sessions (session_id, data) VALUES (?, ?)',
                (session.session_id, session.model_dump_json()),
            )
            await db.commit()

    @classmethod
    async def create_session(cls) -> str:
        session_id = str(uuid4())
        session = UserSession(session_id=session_id)
        await cls.save_session(session)
        return session_id
