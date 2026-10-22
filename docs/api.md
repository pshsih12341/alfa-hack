# API контракт — Кредитный кабинет для малого и среднего бизнеса (МСБ)

> Версия: 0.1.0 (в разработке, stage 1).
> Источник правды: **данный файл**. Код: `backend/app/routers/users.py`, `backend/app/main.py`, `backend/app/models.py`, `backend/app/schemas.py`.
> Бэкенд: FastAPI + SQLAlchemy. Сейчас БД — SQLite (stage 1); целевая — PostgreSQL + Redis (stage 2, см. «Специфика БД»).
> Фронтенд: отдельный проект на React (Vite/CRA), см. `frontend/`. Бэк статику не раздаёт: `GET /` → `404`, UI не отдаётся.

---

## Общее

- Базовый URL: `http://localhost:8000` (на время хакатона).
- Вся API: JSON (UTF-8).
- Схемы (Pydantic) — в `backend/app/schemas.py`.
- Токены сессий — в БД (`sessions`), кука `ck_session`.
- Swagger UI: `http://localhost:8000/docs`, OpenAPI: `http://localhost:8000/openapi.json`.
- Ошибки возвращаются в формате `{"detail": "<текст>"}` со статусом:
  - `400` — клиентская ошибка (например, телефон уже зарегистрирован);
  - `401` — не авторизован (нет cookie, сессия не найдена, сессия истекла, пользователь удалён);
  - `422` — ошибка валидации тела запроса (стандартный ответ FastAPI/Pydantic);
  - `500` — серверная ошибка.

---

## Авторизация

- Включается по куке `ck_session`.
- Кука: HTTP-only, `max-age` = `COOKIE_MAX_AGE` (по умолчанию 30 дней, срок меняется в `.env`), `path=/`, `SameSite=Lax`, `Secure=false` на локальной среде.
- Куку `ck_session` ставят и `POST /api/users/reg`, и `POST /api/users/login`.
- Отдельного эндпоинта для logout/ротации сессии сейчас нет (сделано минимально).

---

## 1. Регистрация

**`POST /api/users/reg`**

Тело `RegisterRequest` (JSON):

| Поле | Тип | Обязательно | Описание | Пример |
|---|---|---|---|---|
| `phoneNumber` | string | да | 11 цифр, обязательно с `7` на первом месте. Нормализуется в формат `+7...` | `"79991234567"` |
| `creditSum` | integer | да | Сумма кредита, руб., ≥ 0 | `1000000` |
| `purpose` | string | да | Цель кредита | `"Пополнение оборотных средств"` |
| `income` | integer | да | Прибыль компании, руб., ≥ 0 | `250000` |
| `inn` | string | нет | ИНН или ОГРН, до 20 символов | `"7707083893"` |

- **Успех:** `201 Created` → `{"clientId": "<uuid>"}` + `Set-Cookie: ck_session=...`. Данные пишутся в `users`.
- **Ошибка:** `400` → `{"detail": "Телефон уже зарегистрирован"}`, если `phoneNumber` уже есть в БД.
- **Ошибка:** `422` → стандартный ответ FastAPI, если тело не соответствует схеме.

Пример запроса:

```http
POST /api/users/reg HTTP/1.1
Content-Type: application/json

{
  "phoneNumber": "79991234567",
  "creditSum": 1000000,
  "purpose": "Пополнение оборотных средств",
  "income": 250000,
  "inn": "7707083893"
}
