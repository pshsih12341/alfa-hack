# Кредитный кабинет для малого и среднего бизнеса (МСБ)

Контролль заявок на кредит: регистрация по номеру телефона, авторизация
(кука `ck_session`, дольшняя — 30 суток), личный кабинет. Бэкенд
(FastAPI + SQLite) отдаёт API и статический фронтенд.

## Состав

- **backend/** — FastAPI-приложение: API, SQLite, раздача статики
- **frontend/** — HTML-интерфейс (отдаётся бэком, не собирается отдельно)
- **docs/** — `api.md` — контракт API

## Быстрый старт

```bash
pip install -r backend/requirements.txt
cd backend
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

В браузере:

- http://localhost:8000/ — фронтенд (регистрация/авторизация/кабинет)
- http://localhost:8000/docs — OpenAPI (Swagger)

## Команда

- belova polina — business analyst
- lisitsyn ivan — backend
- ryskulov ormonkhan — product
- babaev misirkhan — data scientist

## Документация

- Backend: `backend/README.md`
- Frontend: `frontend/README.md`
- API-контракт: `docs/api.md`
