# Кредитный кабинет для малого и среднего бизнеса (МСБ)

Контролль заявок на кредит: регистрация по номеру телефона, авторизация
(кука `ck_session`, дольшняя — 30 суток), личный кабинет. Бэкенд (FastAPI
+ SQLite) — только API, без UI.

## Состав

- **backend/** — FastAPI-приложение: API, SQLite, CORS
- **frontend/** — отдельный проект (Next.js и т.д.), создаёт фронтендер
- **docs/** — `api.md` — контракт API

## Запуск

Проект состоит из двух независимых сервисов. Поднимает каждый разработчик.

### Бэкенд (FastAPI, API + SQLite)

```bash
cd backend
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Порт: `8000`. Документация API: http://localhost:8000/docs

### Фронтенд

Скаффолд создаёт фронтендер (Next.js по умолчанию, порт 3000):

```bash
npx create-next-app@latest frontend
cd frontend
npm run dev
```

Порт уточняется фронтендером (по умолчанию 3000).

## Команда

- belova polina — business analyst
- lisitsyn ivan — backend
- ryskulov ormonkhan — product
- babaev misirkhan — data scientist

## Документация

- Backend: `backend/README.md`
- Frontend: `frontend/README.md`
- API-контракт: `docs/api.md`
- Интеграция фронтенда: `docs/api.md` → раздел «Интеграция фронтенда»
