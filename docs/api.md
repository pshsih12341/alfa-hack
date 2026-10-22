# API контракт — Кредитный кабинет для малого и среднего бизнеса (МСБ)

> Версия: 0.1.0 (пока не финализирована — моки/заглушки в продакшне, пока всё работает в локальной среде).
> Источник правды: **данный файл**. Код: `backend/app/routers/users.py`, `backend/app/main.py`, `backend/app/models.py`.
> Бэкенд: FastAPI + SQLAlchemy (SQLite по умолчанию, `DATABASE_URL` в `.env`).
> Фронтенд: `app/static/index.html`, обслуживается маршрутом `GET /` (backend).

---

## Общее

- Базовый URL: `http://localhost:8000` (на время хакатона).
- Вся API: JSON (UTF-8).
- Схемы (Pydantic) — в `app/schemas.py`.
- Токены сессий — в БД (`sessions`), кука `ck_session`.
- Ошибки возвращаются в формате `{"detail": "<текст>"}` со статусом:
  - `400` — клиентская ошибка (например, телефон уже зарегистрирован);
  - `401` — не авторизован (нет cookie, сессия не найдена, сессия истекла, пользователь удалён);
  - `500` — серверная ошибка.

---

## Авторизация

- Включается по куке `ck_session`.
- Кука: HTTP-only, `max-age` = `COOKIE_MAX_AGE` (по умолчанию 30 дней, срок можно изменить в `.env`), `path=/`, `SameSite=lax`.
- Логин (через `POST /api/users/login`) **устанавливает** куку автоматически.
- Для рояции/закрытия сессии — нет Эндпоинта (сделана минимально).

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

- **Успех:** `201 Created` → `{"clientId": "<uuid>"}`. Данные пишутся в `users`.
- **Ошибка:** `400` → `{"detail": "Телефон уже зарегистрирован"}`, если `phoneNumber` уже есть в БД.

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
```

---

## 2. Авторизация

**`POST /api/users/login`**

Тело `LoginRequest` (JSON):

| Поле | Тип | Обязательно | Описание | Пример |
|---|---|---|---|---|
| `phoneNumber` | string | да | Номер телефона в любом форме (нормализуется) | `"+79991234567"` |

- **Успех:** `200 OK` → `{"clientId": "<uuid>", "isAdmin": true/false}`. Бэк **также устанавливает куку** `ck_session`.
- **Ошибка:** `401` → `{"detail": "Неверный номер телефона"}`, если пользователя с таким номером нет.

Пример запроса:

```http
POST /api/users/login HTTP/1.1
Content-Type: application/json

{
  "phoneNumber": "79991234567"
}
```

Пример ответа:

```json
{
  "clientId": "7820ebd1-5bd8-4057-9c0f-98dd63ba4b32",
  "isAdmin": false
}
```

---

## 3. Текущий пользователь

**`GET /api/users/me`**

Требует куку `ck_session` (авторизация).

- **Успех:** `200 OK` → `UserResponse`:

| Поле | Тип | Описание |
|---|---|---|
| `clientId` | string | UUID клиента |
| `phoneNumber` | string | Нормализованный номер |
| `creditSum` | integer | Сумма кредита |
| `purpose` | string | Цель кредита |
| `income` | integer | Прибыль компании |
| `inn` | string | ИНН/ОГРН |
| `isAdmin` | boolean | Является ли админ |
| `createdAt` | string (ISO 8601) | Дата регистрации |

- **Ошибка:** `401` → `{"detail": "..."}` (не авторизован / сессия не найдена / сессия истекла).

Пример ответа:

```json
{
  "clientId": "7820ebd1-5bd8-4057-9c0f-98dd63ba4b32",
  "phoneNumber": "+79991234567",
  "creditSum": 1000000,
  "purpose": "Пополнение оборотных средств",
  "income": 250000,
  "inn": "7707083893",
  "isAdmin": false,
  "createdAt": "2026-10-22T07:21:52.986736"
}
```

---

## 4. Администратор

- Администраторов **не создаёт API**. Создать вручную в БД можно скриптом:
  ```bash
  python3 scripts/seed_admin.py "+799****7766"
  ```
  (без аргумента — `+790****0000`). Поле `is_admin = true`, остальные поля — пустые.
- Проверить, что пользователь — админ, можно через `isAdmin` в ответе `GET /api/users/me`.

---

## Специфика БД

Таблицы (SQLite): `users` (id, phone_number, credit_sum, purpose, income, inn, is_admin, created_at) и `sessions` (id, client_id, token, created_at, expires_at).
`clientId` — UUID (строка). `phone_number` — уникальный индекс.

---

## Интеграция фронтенда

Фронтенд — отдельный проект (стек — на усмотрение фронтендера, рекомендуется
Next.js, порт 3000 по умолчанию). Бэк не зависит от UI.

### 1. Кука auth

- Имя: `ck_session`, HTTP-only, `SameSite=Lax`, `max-age=30` дней, `Secure=false` (локальная среда).
- При логине бэк устанавливает куку; фронтенд её подхватывает автоматически.

### 2. Источник запросов

**Способ A — dev-proxy (рекомендуется).** В `next.config.js` (или `vite.config.js`)
создаём `rewrites()`, пробрасывающие `/api/*` на бэк:

```js
async rewrites() {
  return [{ source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' }];
}
```

Фронт обращается к `/api/...` (same-origin), кука `ck_session` автоматически
отправляется как same-origin, **CORS вообще не участвует**.

**Способ Б — прямой fetch на `http://localhost:8000`:**

```js
fetch('http://localhost:8000/api/users/me', { credentials: 'include' })
```

Тогда в `backend/.env` должно быть:

```env
CORS_ORIGINS=http://localhost:3000
```

И бэк отдаст `Access-Control-Allow-Origin: http://localhost:3000`
(см. `OPTIONS /api/users/login` в тестах).

### 3. Типы для TS

Сгенерировать из OpenAPI-спецификации бэка:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o types.ts
```

(или `openapi-ts`, `orval` — на вкус команды).

### 4. Пример запроса на стороне фронтенда

```ts
const res = await fetch('/api/users/me', { credentials: 'include' });
const user = await res.json();
```

