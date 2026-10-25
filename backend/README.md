# Backend — FastAPI

API для кредитного кабинета МСБ. Полный контракт — в [`../docs/api.md`](../docs/api.md).

---

## Содержание

1. [Стек](#стек)
2. [Структура](#структура)
3. [Запуск в compose](#запуск-в-compose)
4. [Локальная разработка](#локальная-разработка)
5. [Миграции](#миграции)
6. [Скрипты](#скрипты)
7. [Mock-скоринг](#mock-скоринг)
8. [Переменные окружения](#переменные-окружения)
9. [Troubleshooting](#troubleshooting)

---

## Стек

| Компонент | Версия | Назначение |
|---|---|---|
| Python | 3.12 | рантайм |
| FastAPI | 0.115+ | веб-фреймворк |
| Pydantic | 2.x | валидация схем |
| SQLAlchemy | 2.x | ORM |
| Alembic | 1.13+ | миграции |
| PostgreSQL | 16 | БД (в compose на `5433`) |
| Redis | 7 | зарезервирован (этап 3) |

---

## Структура

```
backend/
├── app/
│   ├── main.py             FastAPI-приложение, CORS, роутеры
│   ├── config.py           настройки из .env (Pydantic Settings)
│   ├── database.py         engine, SessionLocal, Base, utcnow
│   ├── models.py           User, Session, Product, Application,
│   │                       ApplicationStatusHistory, PaymentOrder
│   ├── schemas.py          Pydantic-схемы запросов и ответов
│   ├── auth.py             create_session, get_current_user, cookie helpers
│   ├── session_store.py    SessionStore (Protocol) + DBSessionStore
│   ├── scoring.py          mock-скоринг (детерминированный, 5 сек)
│   ├── cache.py            CacheBackend + InMemoryCache (этап 3 — Redis)
│   └── routers/
│       ├── users.py            /api/users/*
│       ├── applications.py     /api/applications/*
│       └── admin.py            /api/admin/*
├── migrations/             Alembic (versions/ — миграции)
├── scripts/
│   ├── seed_products.py    идемпотентно засеивает products
│   └── seed_admin.py       создаёт админа по номеру телефона
├── Dockerfile
├── entrypoint.sh           alembic upgrade + seed_products + uvicorn
├── alembic.ini
├── requirements.txt
├── .env.docker.example     шаблон для локальной разработки
└── README.md
```

---

## Запуск в compose

Из **корня** репозитория:

```bash
docker compose up --build
```

Бэк поднимется на `http://localhost:8000`, Swagger — `/docs`.

При старте контейнера `entrypoint.sh` выполняет:

1. `alembic upgrade head` — миграции
2. `python scripts/seed_products.py` — продукты
3. `uvicorn app.main:app --host 0.0.0.0 --port 8000`

Логи:

```bash
docker compose logs -f backend
```

---

## Локальная разработка

Без пересборки контейнера, для быстрых итераций.

### 1. Инфраструктура

```bash
cd ..
docker compose up -d postgres redis
```

Postgres — на `localhost:5433`, Redis — внутри сети compose.

### 2. Настроить `.env`

```bash
cd backend
cp .env.docker.example .env
```

В `.env` заменить:

```diff
- DATABASE_URL=postgresql+psycopg2://credit_kiosk:credit_kiosk@postgres:5432/credit_kiosk
+ DATABASE_URL=postgresql+psycopg2://credit_kiosk:credit_kiosk@localhost:5433/credit_kiosk

- REDIS_URL=redis://redis:6379/0
+ REDIS_URL=redis://localhost:6379/0
```

### 3. Миграции и seed

```bash
alembic upgrade head
python scripts/seed_products.py
```

### 4. Запуск

```bash
uvicorn app.main:app --port 8000 --reload
```

Swagger: `http://localhost:8000/docs`

---

## Миграции

### Создать

После правки `models.py`:

```bash
alembic revision --autogenerate -m "краткое описание"
```

### Проверить **перед** `upgrade`

```bash
grep -E "op\.(create_table|drop_table|add_column|drop_column)" \
  migrations/versions/<hash>_*.py
```

**Проверить глазами:**

| Признак | Диагноз |
|---|---|
| `op.drop_table('users')` в `upgrade()` | ❌ сломает всё, откатить |
| `op.drop_table('sessions')` в `upgrade()` | ❌ сломает auth, откатить |
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

### Проверить колонки в БД

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

- Идемпотентно: `update` или `insert` по `code`.
- Запускать после миграций.
- Сейчас создаёт только `no_collateral` (100k–30M, 6–36 мес, ставка 19%).

### Seed админа

```bash
python scripts/seed_admin.py +79990009999
```

- Создаёт `User` с `is_admin=true`.
- Если пользователь уже есть — поднимает флаг.
- Вход админа — тот же `POST /api/users/login` по номеру,
  `isAdmin:true` в ответе.

---

## Mock-скоринг

`app/scoring.py` — заглушка (5 секунд):

```
creditSum <= 30_000_000  →  SUCCESS + product_id = no_collateral
иначе                    →  REJECTED
```

**Детерминированно**, без `random` — жюри получит одинаковый ответ на
одинаковый запрос.

При создании заявки запускается как `BackgroundTasks` — не блокирует
ответ клиенту.

Когда ML-сервис будет готов — тело `run_scoring` заменится на HTTP-вызов
`POST /score` с переключателем `SCORING_MODE=ml`. Интерфейс
(`application_id` → обновление статуса в БД) сохранится.

---

## Переменные окружения

Все в `app/config.py` (`Settings`), читаются из `.env`.

| Переменная | Дефолт | Описание |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./credit_kiosk.db` | локально — Postgres на `localhost:5433` |
| `REDIS_URL` | `redis://localhost:6379/0` | зарезервировано |
| `COOKIE_NAME` | `ck_session` | имя cookie |
| `COOKIE_MAX_AGE` | `2592000` (30 дней) | TTL сессии |
| `COOKIE_SECURE` | `false` | `true` — только для HTTPS |
| `COOKIE_SAME_SITE` | `lax` | `lax` / `strict` / `none` |
| `CORS_ORIGINS` | `:5173, :3000, :8080` | список через запятую |
| `AUTO_CREATE_TABLES` | `false` | **не включать**, схема через Alembic |

---

## Troubleshooting

### `alembic current` → `connection refused`

`.env` смотрит на несуществующий Postgres.

```bash
# проверить, что контейнерный Postgres поднят
docker compose ps postgres
sudo ss -tlnp | grep 5433

# проверить, что читается из .env
python -c "from app.config import settings; print(repr(settings.DATABASE_URL))"
```

Должно быть `...@localhost:5433/credit_kiosk`. **Не** `localhost:5432` —
там системный Postgres, он вне проекта.

### `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL`

Битая строка в `.env`. Часто — дубль `DATABASE_URL=DATABASE_URL=...` или
кавычки.

```bash
grep -c '^DATABASE_URL=' .env    # должно быть ровно 1
```

### `entrypoint.sh: not found`

CRLF-переносы:

```bash
sed -i 's/\r$//' entrypoint.sh
docker compose up --build backend
```

### `permission denied to create database`

Роль `credit_kiosk` не имеет прав на `CREATE DATABASE`.

```bash
sudo -u postgres psql -c "CREATE DATABASE credit_kiosk OWNER credit_kiosk;"
```

### `alembic upgrade` падает на `UndefinedColumn`

Код обновлён, миграция не применена. Применить:

```bash
alembic upgrade head
```

Если локально всё ок, а в compose падает — пересобрать:
`docker compose up --build backend`.

---

## Ссылки

- Контракт API: [`../docs/api.md`](../docs/api.md)
- Корневой README: [`../README.md`](../README.md)
- Swagger: `http://localhost:8000/docs`