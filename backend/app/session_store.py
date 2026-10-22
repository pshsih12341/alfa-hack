"""Хранилище сессий.

Слой абстракции: в stage 2 DB-реализацию заменим на Redis без изменений в роутерах.
"""

import secrets
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, select

from .database import SessionLocal, utcnow
from .models import Session as DBSession


class SessionStore(Protocol):
    def create(self, user_id: str, ttl: int) -> str: ...
    def get(self, session_id: str) -> str | None: ...
    def delete(self, session_id: str) -> None: ...


class DBSessionStore:
    """Текущая реализация: сессия в таблице sessions."""

    def create(self, user_id: str, ttl: int) -> str:
        token = secrets.token_hex(32)
        now = utcnow()
        session = DBSession(
            id=secrets.token_hex(8),
            client_id=user_id,
            token=token,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        with SessionLocal() as db:
            db.add(session)
            db.commit()
        return token

    def get(self, session_id: str) -> str | None:
        with SessionLocal() as db:
            session = db.execute(
                select(DBSession).where(DBSession.token == session_id)
            ).scalar_one_or_none()
            if session is None or session.expires_at < utcnow():
                return None
            return session.client_id

    def delete(self, session_id: str) -> None:
        with SessionLocal() as db:
            db.execute(delete(DBSession).where(DBSession.token == session_id))
            db.commit()


def create_session_store() -> SessionStore:
    return DBSessionStore()