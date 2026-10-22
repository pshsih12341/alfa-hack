from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config, models
from .database import SessionLocal
from .session_store import SessionStore, create_session_store


def get_session_store() -> SessionStore:
    return create_session_store()


def create_session(store: SessionStore, client_id: str, ttl: int) -> str:
    """Токен создаёт store — он же и возвращается в cookie."""
    return store.create(client_id, ttl)


def get_current_user(
    request: Request,
    store: SessionStore = Depends(get_session_store),
) -> models.User:
    token = request.cookies.get(config.settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user_id = store.get(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Сессия не найдена")
    with SessionLocal() as db:
        user = db.get(models.User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        return user


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