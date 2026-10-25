# Кредитный кабинет для малого и среднего бизнеса (МСБ)

Сервис подачи заявок на кредит: регистрация по номеру телефона, авторизация,
личный кабинет с заявками, админ-панель. Скоринг — отдельный ML-сервис
с кредитной моделью (стоп-правила, риск, DSCR, подбор суммы и срока).

Всё поднимается одной командой `docker compose --profile ml up`.

---

## Содержание

1. [Состав репозитория](#состав-репозитория)
2. [Запуск для проверяющих](#запуск-для-проверяющих)
3. [Запуск без ML (mock)](#запуск-без-ml-mock)
4. [Demo-ИНН для защиты](#demo-инн-для-защиты)
5. [Статусы заявки](#статусы-заявки)
6. [Продукты](#продукты)
7. [Локальная разработка](#локальная-разработка)
8. [Troubleshooting](#troubleshooting)

---

## Состав репозитория

```
.
├── backend/          FastAPI — API
│   ├── app/          код (routers, models, schemas, auth, scoring)
│   ├── migrations/   Alembic
│   ├── scripts/      seed_products.py, seed_admin.py
│   ├── Dockerfile
│   └── entrypoint.sh  alembic upgrade + seed + uvicorn
├── ml/               ML-сервис (FastAPI, порт 8001)
│   ├── src/alfa_ml/
│   ├── config/scoring.yaml
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/         React (Vite) + nginx
│   ├── src/
│   ├── Dockerfile
│   └── nginx.conf
├── docs/
│   └── api.md        контракт API (единственный источник правды)
├── mocks/
│   └── mocks_postgres.sql   12 таблиц, 2000 компаний для ML
└── docker-compose.yml
```

---

## Запуск для проверяющих

Требуется **Docker** и **Docker Compose v2**.

```bash
git clone <repo-url>
cd alfa-hack
docker compose --profile ml up --build
```

Первый запуск — 3–5 минут (сборка 3 образов, init Postgres, загрузка моков).
Дальше — секунды.

Открыть в браузере: **http://localhost:8080**

Swagger backend: **http://localhost:8000/docs**

### Что внутри

| Сервис | Образ | Назначение |
|---|---|---|
| `frontend` | nginx + React | UI, `/api` проксирует на `backend:8000` |
| `backend` | python:3.12-slim | API, при старте миграции + seed продуктов |
| `ml` | python + uv | ML-скоринг: `/score`, `/companies/{inn}` |
| `postgres` | postgres:16 | две базы: `credit_kiosk` (основная) + `mocks` (для ML) |
| `redis` | redis:7 | зарезервирован под сессии (этап 3) |

### Порты на хосте

| Порт | Сервис | Назначение |
|---|---|---|
| `8080` | frontend | UI, `/api` → backend |
| `8000` | backend | Swagger backend |
| `5433` | postgres | для локальной отладки |
| `8001` | — | ML-сервис, только внутри compose-сети (`http://ml:8001`) |
| `6379` | — | Redis, только внутри compose-сети |

### Пересоздать БД с нуля

```bash
docker compose --profile ml down -v
docker compose --profile ml up --build
```

`-v` удаляет том `pgdata` — Postgres пересоздаст обе базы и загрузит моки из
`mocks/mocks_postgres.sql`.

---

## Запуск без ML (mock)

Если ML-сервис недоступен или нужен быстрый старт без моков:

```bash
docker compose up --build
```

В `backend.environment` должен быть `SCORING_MODE: mock` — детерминированная
заглушка (SUCCESS если `creditSum <= 30 000 000`, иначе REJECTED). Без `/score`,
без моков.

---

## Demo-ИНН для защиты

ML гарантирует сценарий для этих ИНН. **Все ИНН — строкой** (ИНН с ведущим нулём
при передаче числом теряет ноль).

| Сценарий | ИНН | Сумма | Срок | Статус |
|---|---|---|---|---|
| APPROVED | `7476595370` | 2 450 000 | 24 | SUCCESS |
| APPROVED | `5298426141` | 1 900 000 | 24 | SUCCESS |
| APPROVED | `3614154174` | 30 000 000 | 18 | SUCCESS |
| OFFER | `5483374635` | 4 100 000 | 12 | OFFER |
| OFFER | `5077083048` | 12 750 000 | 6 | OFFER |
| REJECTED (Росфинмониторинг) | `669985868171` | любая | любой | REJECTED |
| REJECTED (банкротство) | `661208802049` | любая | любой | REJECTED |
| REJECTED (риск PD>30%) | `639038602581` | 350 000 | 12 | REJECTED |
| INFO (этап 2) | `5991587272` | 1 050 000 | 18 | INFO |

Цель — любая, кроме `refinancing`. `revenueLast12m` не влияет — у всех demo-ИНН
выручка уже есть в источниках (`revenueKnown=true`).

Подробности — `docs/api.md`, раздел «ML-интеграция».

---

## Статусы заявки

```
PRESCORING → SCORING → SUCCESS | REJECTED | INFO | OFFER
SUCCESS   → AWAITING_DISBURSEMENT → COMPLETED
OFFER     → AWAITING_DISBURSEMENT   (accept-offer)
INFO      → PRESCORING              (этап 2)
```

| Статус | Что значит | Кто переводит |
|---|---|---|
| `PRESCORING` | создана, скоринг в очереди | backend при создании |
| `SCORING` | зарезервирован под streaming ML | — |
| `SUCCESS` | одобрено, продукт выбран | ML `decision: APPROVED` |
| `REJECTED` | отказ | ML `decision: REJECTED` |
| `INFO` | нужны документы (этап 2) | ML `decision: INFO` |
| `OFFER` | предложены варианты | ML `decision: OFFER` |
| `AWAITING_DISBURSEMENT` | условия приняты, создано поручение | `accept` / `accept-offer` |
| `COMPLETED` | админ подтвердил | `POST /admin/.../complete` |

Переходы `PRESCORING → SUCCESS/REJECTED/INFO/OFFER` делает ML через `/score`.

---

## Продукты

| code | name | rate | limit | term |
|---|---|---|---|---|
| `no_collateral` | Кредит для бизнеса без залога | из ML (18–24% по риску) | 100 000 – 30 000 000 | 6–36, шаг 6 |

`collateral` (под залог) — legacy в БД, скоринг его не выбирает.

Seed: `backend/scripts/seed_products.py` (идемпотентный, запускается в entrypoint).

---

## Локальная разработка

### Backend

```bash
docker compose up -d postgres redis
cd backend
cp .env.docker.example .env
# в .env: @postgres: → @localhost:5433, redis: → localhost:6379
alembic upgrade head
python scripts/seed_products.py
uvicorn app.main:app --port 8000 --reload
```

Swagger: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite на `:5173`, прокси `/api` → `:8000` в `vite.config.ts`.

### ML

```bash
cd ml
uv sync --frozen
uvicorn alfa_ml.service.app:app --port 8001 --reload
```

Требует `ML_DATABASE_URL` на `localhost:5433/mocks`.

---

## Troubleshooting

### `address already in use`

```bash
sudo ss -tlnp | grep -E "5433|8000|8080|6379"
```

- `8000` — `pkill -f "uvicorn app.main:app"`
- `8080` — остановить другой веб-сервер
- `5433` — `sudo systemctl stop postgresql`
- `6379` — убрать `ports` у Redis в compose

### `database "mocks" does not exist`, ML `/health` → 503

Том `pgdata` существовал до `mocks_postgres.sql`. Накатить вручную:

```bash
docker compose exec postgres psql -U credit_kiosk -d credit_kiosk \
  -f /docker-entrypoint-initdb.d/20_mocks.sql
```

Идемпотентно, безопасно повторять.

### `alembic current` → `connection refused`

`.env` смотрит на несуществующий Postgres. Для локальной разработки — `localhost:5433`.

### `entrypoint.sh: not found`

CRLF-переносы:

```bash
sed -i 's/\r$//' backend/entrypoint.sh
docker compose --profile ml up -d --build backend
```

---

## Что сделано / что осталось

### Сделано

- Auth: reg, login, logout, `/me`
- Заявки: список, создание, детали, accept (SUCCESS), accept-offer (OFFER)
- Админ: список с фильтром по датам, детали, complete
- ML: `/score`, offer-флоу, fallback на таймауте
- Моки внешних источников (12 таблиц, 2000 компаний)
- Docker-стек: `--profile ml`, entrypoint с миграциями и seed

### В работе (этап 3)

- `INFO`-флоу (дозапрос выписок / `useAlfaAccount`)
- Прокси `/api/companies/{inn}` и `/loans`
- `RedisSessionStore` — сессии в Redis
- Аудит-лог действий администратора