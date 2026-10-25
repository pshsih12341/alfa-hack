# Backend — FastAPI

API для кредитного кабинета МСБ. Контракт — [`../docs/api.md`](../docs/api.md).

---

## Содержание

1. [Стек](#стек)
2. [Структура](#структура)
3. [Запуск в compose](#запуск-в-compose)
4. [Локальная разработка](#локальная-разработка)
5. [Миграции](#миграции)
6. [Скрипты](#скрипты)
7. [Скоринг](#скоринг)
8. [Переменные окружения](#переменные-окружения)
9. [Troubleshooting](#troubleshooting)

---

## Стек

| Компонент | Версия | Назначение |
|---|---|---|
| Python | 3.12 | рантайм |
| FastAPI | 0.115+ | веб-фреймворк |
| Pydantic | 2.x | валидация |
| SQLAlchemy | 2.x | ORM |
| Alembic | 1.13+ | миграции |
| PostgreSQL | 16 | БД (в compose на `5433`) |
| httpx | 0.28+ | клиент к ML-сервису |
| Redis | 7 | зарезервирован (этап 3) |

---

## Структура

```
backend/
├── app/
│   ├── main.py             FastAPI, CORS, роутеры
│   ├── config.py           настройки из .env
│   ├── database.py         engine, SessionLocal, Base, utcnow
│   ├── models.py           User, Session, Product, Application,
│   │                       ApplicationStatusHistory, PaymentOrder
│   ├── schemas.py          Pydantic-схемы
│   ├── auth.py             create_session, get_current_user, cookie
│   ├── session_store.py    SessionStore (Protocol) + DBSessionStore
│   ├── scoring.py          mock/ml скоринг, httpx → /score
│   ├── cache.py            CacheBackend (этап 3 — Redis)
│   └── routers/
│       ├── users.py            /api/users/*
│       ├── applications.py     /api/applications/*
│       └── admin.py            /api/admin/*
├── migrations/             Alembic
├── scripts/
│   ├── seed_products.py    идемпотентно засеивает products
│   └── seed_admin.py       создаёт админа
├── Dockerfile
├── entrypoint.sh           alembic + seed + uvicorn
├── alembic.ini
├── requirements.txt
├── .env.docker.example
└── README.md
```

---

## Запуск в compose

Из корня:

```bash
docker compose --profile ml up --build
```

Бэк на `http://localhost:8000`, Swagger — `/docs`.

`entrypoint.sh` при старте:
1. `alembic upgrade head`
2. `python scripts/seed_products.py`
3. `uvicorn app.main:app --host 0.0.0.0 --port 8000`

Логи: `docker compose logs -f backend`.

---

## Локальная разработка

```bash
# 1. инфраструктура
cd ..
docker compose up -d postgres redis

# 2. настройки
cd backend
cp .env.docker.example .env
# в .env: @postgres: → @localhost:5433, redis: → localhost:6379

# 3. миграции и seed
alembic upgrade head
python scripts/seed_products.py

# 4. запуск
uvicorn app.main:app --port 8000 --reload
```

Swagger: http://localhost:8000/docs

---

## Миграции

### Создать

```bash
alembic revision --autogenerate -m "краткое описание"
```

### Проверить **перед** `upgrade`

```bash
grep -E "op\.(create_table|drop_table|add_column|drop_column)" \
  migrations/versions/<hash>_*.py
```

| Признак | Диагноз |
|---|---|
| `op.drop_table('users')` в `upgrade()` | ❌ сломает всё |
| `op.drop_table('sessions')` в `upgrade()` | ❌ сломает auth |
| пустой `def upgrade(): pass` | ❌ `target_metadata` не подхватил модели |
| только `op.add_column(...)` | ✅ норма |

Если `upgrade()` пустой — проверь `migrations/env.py`:

```python
from app import models  # noqa: F401
target_metadata = Base.metadata
```

### Применить

```bash
alembic upgrade head
alembic current    # head = последняя ревизия
```

### Проверить колонки

```bash
PGPASSWORD=credit_kiosk psql -h 127.0.0.1 -p 5433 -U credit_kiosk \
  -d credit_kiosk -c "\d applications"
```

---

## Скрипты

### Seed продуктов

```bash
python scripts/seed_products.py
```

Идемпотентно (update или insert по `code`). Запускать после миграций. Создаёт
`no_collateral` (100k–30M, 6–36 мес).

### Seed админа

```bash
python scripts/seed_admin.py +79990009999
```

Создаёт `User` с `is_admin=true`. Если пользователь есть — поднимает флаг.
Вход — тот же `POST /api/users/login`, `isAdmin:true` в ответе.

---

## Скоринг

Два режима (`SCORING_MODE` в `.env`/compose):

### `mock`

Детерминированная заглушка:
- `creditSum <= limit_max` → `SUCCESS` + `product_id = no_collateral`
- иначе → `REJECTED`

Не требует ML-сервиса. Запуск: `docker compose up`.

### `ml`

`httpx.post(SCORING_URL + "/score", json=payload, timeout=5)`.

**При ошибке/таймауте:** заявка остаётся в `PRESCORING`, в логе
`ML /score failed for application ... — оставляем в PRESCORING`. Без автоотказа.

**При успехе:**
- ответ ML сохраняется в `applications.scoring_response` (JSON)
- `decision` маппится: `APPROVED → SUCCESS`, `OFFER → OFFER`, `INFO → INFO`, `REJECTED → REJECTED`
- для `SUCCESS`: `product_id = no_collateral`, `rate` из ML
- для `OFFER`: `GET /applications/{id}` читает `offers[]`, `maxByTerm[]`, `limit`, `termLimit`, `clientMessage` из `scoring_response`

При `ml` нужен запущенный ML: `docker compose --profile ml up`.

---

## Переменные окружения

Все в `app/config.py` (`Settings`), читаются из `.env`.

| Переменная | Дефолт | Описание |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./credit_kiosk.db` | локально — `localhost:5433` |
| `REDIS_URL` | `redis://localhost:6379/0` | зарезервировано |
| `COOKIE_NAME` | `ck_session` | имя cookie |
| `COOKIE_MAX_AGE` | `2592000` (30 дней) | TTL сессии |
| `COOKIE_SECURE` | `false` | `true` — только HTTPS |
| `COOKIE_SAME_SITE` | `lax` | `lax`/`strict`/`none` |
| `CORS_ORIGINS` | `:5173, :3000, :8080` | через запятую |
| `AUTO_CREATE_TABLES` | `false` | **не включать**, схема через Alembic |
| `SCORING_MODE` | `mock` | `mock` — заглушка, `ml` — HTTP в ML |
| `SCORING_URL` | `http://ml:8001` | адрес ML-сервиса в compose |
| `SCORING_TIMEOUT_SECONDS` | `5.0` | таймаут `/score`; при превышении — PRESCORING |

---

## Troubleshooting

### `alembic current` → `connection refused`

`.env` смотрит на несуществующий Postgres. Проверь `localhost:5433` (не `5432`).

```bash
docker compose ps postgres
sudo ss -tlnp | grep 5433
python -c "from app.config import settings; print(repr(settings.DATABASE_URL))"
```

### `Could not parse SQLAlchemy URL`

Битая строка в `.env`, часто дубль `DATABASE_URL=DATABASE_URL=...`.

```bash
grep -c '^DATABASE_URL=' .env    # ровно 1
```

### `entrypoint.sh: not found`

```bash
sed -i 's/\r$//' entrypoint.sh
docker compose --profile ml up -d --build backend
```

### `permission denied to create database`

```bash
sudo -u postgres psql -c "CREATE DATABASE credit_kiosk OWNER credit_kiosk;"
```

### `NameError: OfferInfo` при импорте `schemas.py`

`OfferInfo` и `MaxByTermItem` должны быть **выше** `ApplicationDetails`
(Python выполняет файл сверху вниз).
