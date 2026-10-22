import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import models, config
from .database import SessionLocal

AUTH_COOKIE = "ck_session"


def generate_token() -> str:
    return secrets.token_hex(32)


def create_session(client_id: str, expires_in_seconds: int) -> str:
    token = generate_token()
    now = datetime.now()
    session = models.Session(
        id=secrets.token_hex(8),
        client_id=client_id,
        token=token,
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in_seconds),
    )
    with SessionLocal() as db:
        db.add(session)
        db.commit()
    return token


def _set_auth_cookie(response: JSONResponse, token: str) -> JSONResponse:
    response.set_cookie(
        key=config.settings.COOKIE_NAME,
        value=token,
        max_age=config.settings.COOKIE_MAX_AGE,
        httponly=True,
        secure=config.settings.COOKIE_SECURE,
        samesite=config.settings.COOKIE_SAME_SITE,
        path="/",
    )
    return response


def get_current_user(request: Request) -> models.User:
    token = request.cookies.get(config.settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    with SessionLocal() as db:
        session = db.execute(
            select(models.Session).where(models.Session.token == token)
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=401, detail="Сессия не найдена")
        if session.expires_at < datetime.now():
            raise HTTPException(status_code=401, detail="Сессия истекла")
        user = db.get(models.User, session.client_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        return user
