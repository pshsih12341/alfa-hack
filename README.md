# Кредитный кабинет для малого и среднего бизнеса (МСБ)

Контроль заявок на кредит: регистрация по номеру телефона, авторизация
(кука `ck_session`, долгоживущая — 30 суток), личный кабинет.
Бэкенд (FastAPI + SQLAlchemy) — только API, без UI.

## Состав

- `backend/` — FastAPI-приложение: API, SQLite (stage 1), CORS, Alembic-миграции
- `frontend/` — отдельный проект на React (Vite/CRA), создаёт фронтендер
- `docs/api.md` — контракт API (единственный источник правды)

## Архитектура

Два независимых сервиса:

- **backend** — чистое API. `GET /` отдаёт `404` (статику не раздаёт).
  Точки входа — `/docs` (Swagger) и `/api/*`.
- **frontend** — отдельный проект, ходит в API либо через dev-proxy
  (`/api` → `:8000`), либо напрямую с `credentials: 'include'`.
  Подробности — `docs/api.md`, раздел «Интеграция фронтенда».

Сейчас (stage 1) БД — SQLite, чтобы быстро стартовать.
Целевая архитектура (stage 2): **PostgreSQL** (основная БД, ACID,
конкурентность) + **Redis** (сессии, кэш). Заготовки для перехода уже в коде:
`docker-compose.yml`, `backend/app/session_store.py`, `backend/app/cache.py`,
`alembic`.

## Запуск

### Бэкенд (FastAPI, API + SQLite)

```bash
cd backend
cp .env.example .env
alembic upgrade head          # создать схему (users, sessions)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
# Команда

- belova polina — business analyst
- lisitsyn ivan — backend
- ryskulov ormonkhan — product
- babaev misirkhan — data scientist
- ishbylatov ildar - frontend

