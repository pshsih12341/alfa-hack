# Бэкенд — как запустить

## Запуск

```bash
cd backend
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Документация API: http://localhost:8000/docs

## Переменные окружения

См. `backend/.env.example`. Часто используемые:

- `DATABASE_URL` — SQLite по умолчанию (`sqlite:///./credit_kiosk.db`)
- `COOKIE_NAME` — имя куки авторизации (`ck_session`)
- `COOKIE_MAX_AGE` — срок жизни куки, секунды (по умолчанию 30 дней)
- `COOKIE_SECURE` — `true` только по HTTPS в продакшне
- `COOKIE_SAME_SITE` — `lax` по умолчанию

## Фронтенд

HTML-интерфейс хранится в `backend/app/static/index.html` и отдаётся
бэком по роуту `GET /`. Бэк не использует отдельный фронтенд-сервер.

## Админка

Админов создаются вручную в БД:

```bash
cd backend
python3 scripts/seed_admin.py +799****7766
```

## Тесты

`backend/tests/` — пока пустой (например, можно добавить парные тесты
на `POST /api/users/reg` и `POST /api/users/login`).
