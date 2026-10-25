# Кредитный кабинет для малого и среднего бизнеса (МСБ)

Сервис подачи заявок на кредит: регистрация по номеру телефона, авторизация
(кука `ck_session`, долгоживущая — 30 суток), личный кабинет с заявками,
админ-панель для сотрудника банка.

Бэкенд — FastAPI + SQLAlchemy + Alembic. Фронтенд — React (Vite). Всё
поднимается одной командой `docker compose up` и работает у проверяющих
без ручной настройки.

---

## Состав репозитория

```
.
├── backend/          FastAPI-приложение
│   ├── app/          код API (routers, models, schemas, auth, scoring)
│   ├── migrations/   Alembic-миграции
│   ├── scripts/      seed_products.py, seed_admin.py
│   ├── Dockerfile
│   └── entrypoint.sh  alembic upgrade + seed + uvicorn при старте
├── frontend/         React-приложение (Vite)
│   ├── Dockerfile    multi-stage: node build → nginx
│   └── nginx.conf    проксирует /api → backend:8000
├── docs/
│   └── api.md        контракт API (единственный источник правды)
├── mocks/            данные моков внешних источников (ML, отдельная ветка)
└── docker-compose.yml
```

---

## Запуск (для проверяющих)

Требуется **Docker** и **Docker Compose v2**. Всё поднимается одной командой:

```bash
git clone <repo-url>
cd alfa-hack
docker compose up --build
```

Первый запуск — 2–3 минуты (сборка образов, инициализация Postgres).
Дальше — секунды.

Открыть в браузере: **http://localhost:8080**

Swagger API: **http://localhost:8000/docs**

### Что внутри

- **frontend** (nginx) — React-приложение, проксирует `/api` на `backend:8000`
- **backend** (FastAPI) — API, при старте сам накатывает миграции и seed продуктов
- **postgres** — основная БД `credit_kiosk`; при первом старте грузит моки
  (`mocks/mocks_postgres.sql`, если файл присутствует)
- **redis** — зарезервирован под серверные сессии (этап 3)

### Порты на хосте

| Порт | Сервис | Назначение |
|---|---|---|
| `8080` | frontend | UI, `/api` проксируется на backend |
| `8000` | backend | Swagger, прямые запросы к API |
| `5433` | postgres | для локальной отладки; `5432` обычно занят системным Postgres |
| `6379` | — | не проброшен, Redis доступен только внутри compose-сети |

Если порт занят, поменяйте `ports` в `docker-compose.yml`.

### Пересоздать БД с нуля

```bash
docker compose down -v      # -v удаляет том pgdata
docker compose up --build
```

---

## Локальная разработка бэкенда

Без пересборки контейнера бэка — удобно для итераций.

### 1. Поднять инфраструктуру

```bash
docker compose up -d postgres redis
```

Postgres будет доступен на `localhost:5433`.

### 2. Настроить `.env`

```bash
cd backend
cp .env.docker.example .env
```

В `.env` замените `@postgres:` на `@localhost:5433` и `redis:` на `localhost:6379`:

```env
DATABASE_URL=postgresql+psycopg2://credit_kiosk:credit_kiosk@localhost:5433/credit_kiosk
REDIS_URL=redis://localhost:6379/0
```

### 3. Накатить миграции и seed

```bash
alembic upgrade head
python scripts/seed_products.py
```

### 4. Запустить бэк

```bash
uvicorn app.main:app --port 8000 --reload
```

Swagger: http://localhost:8000/docs

### 5. Создать админа (один раз)

```bash
python scripts/seed_admin.py +79990009999
```

Пароля нет — вход по номеру телефона, как у клиентов.

---

## Локальная разработка фронтенда

Фронтендер работает в `frontend/` независимо от compose.

```bash
cd frontend
npm install
npm run dev
```

Vite поднимется на `http://localhost:5173`. Прокси на бэк — в `vite.config.ts`:

```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
  },
},
```

Тогда cookie `ck_session` отправляется автоматически (same-origin для браузера).

---

## Контракт API

Единственный источник правды — **`docs/api.md`**. Оттуда же генерируются
TS-типы для фронта:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

Кратко — что есть:

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/users/reg` | Регистрация + первая заявка |
| POST | `/api/users/login` | Вход |
| POST | `/api/users/logout` | Выход |
| GET | `/api/users/me` | Текущий пользователь |
| GET | `/api/applications` | Список заявок клиента |
| POST | `/api/applications` | Новая заявка |
| GET | `/api/applications/{id}` | Детали заявки |
| POST | `/api/applications/{id}/accept` | Принять условия (SUCCESS) |
| POST | `/api/applications/{id}/additional-info` | Доп. данные (INFO, этап 2) |
| POST | `/api/applications/{id}/accept-offer` | Выбрать вариант (OFFER, этап 2) |
| GET | `/api/admin/applications` | Список всех заявок (админ) |
| GET | `/api/admin/applications/{id}` | Детали (админ) |
| POST | `/api/admin/applications/{id}/complete` | Завершить (админ) |

---

## Статусы заявки

```
PRESCORING → SCORING → SUCCESS | REJECTED | INFO | OFFER
SUCCESS   → AWAITING_DISBURSEMENT → COMPLETED
OFFER     → AWAITING_DISBURSEMENT   (при accept-offer)
INFO      → PRESCORING              (после доп. данных, этап 2)
```

- `PRESCORING` — заявка создана, скоринг в очереди
- `SCORING` — зарезервирован под реальный ML
- `SUCCESS` — одобрено, продукт выбран
- `REJECTED` — отказ
- `INFO` — нужны документы (этап 2)
- `OFFER` — предложены варианты (этап 2, контракт в `docs/api.md`)
- `AWAITING_DISBURSEMENT` — условия приняты, создано платёжное поручение
- `COMPLETED` — админ подтвердил исполнение

**Mock-скоринг** (текущее состояние): через 5 секунд после создания заявки
переводит её в `SUCCESS` (если `creditSum <= 30 000 000`) или `REJECTED`.
Детерминированно, без random — жюри получит одинаковый ответ на одинаковый
запрос.

---

## Продукты

Сейчас используется один продукт:

| code | name | rate | limit | term |
|---|---|---|---|---|
| `no_collateral` | Кредит для бизнеса без залога | 19% | 100 000 – 30 000 000 | 6–36 мес, шаг 6 |

`collateral` (под залог) остаётся в БД для совместимости со старыми заявками,
но скоринг его **не выбирает** — по решению ML в текущей логике продукта
под залог нет.

Seed-скрипт идемпотентный — можно запускать повторно, обновляет по `code`.

---

## Этап 3 — ML-сервис

Отдельная ветка `ml/scoring` (ML-разработчик). В `develop` будет влит как
отдельный сервис в compose с профилем `ml`.

### Что появится

- ML-сервис на `http://ml:8001`:
  - `POST /score` — кредитное решение (APPROVED / OFFER / INFO / REJECTED),
    ставка по риску, лимиты, помесячный платёж
  - `GET /companies/{inn}` — карточка компании для анкеты
  - `GET /companies/{inn}/loans` — кредиты из БКИ для рефинансирования
- Бэк будет проксировать `/api/companies/*` → ML
- Бэк будет звать `/score` вместо mock-скоринга

### Переключатель режима

```env
SCORING_MODE=mock   # текущая заглушка (детерминированная)
SCORING_MODE=ml     # реальный ML-сервис, нужен профиль ml в compose
```

Запуск с ML:

```bash
docker compose --profile ml up --build
```

Если ML-сервис не ответил за 5 секунд — заявка остаётся в `PRESCORING`
(без автоотказа), фон делает retry.

### Моки внешних источников

`mocks/mocks_postgres.sql` создаёт БД `mocks` с 12 таблицами внешних
источников (ЕГРЮЛ, БКИ, ФНС, Росфинмониторинг и др.) и 2 000 синтетических
компаний на дату среза `2026-11-01`. Загружается автоматически при первом
старте Postgres-контейнера, если файл присутствует.

Ручная загрузка (для локального Postgres):

```bash
sudo -u postgres psql -f mocks/mocks_postgres.sql
```

---

## Troubleshooting

### `docker compose up` падает на `address already in use`

На хосте занят порт. Проверьте:

```bash
sudo ss -tlnp | grep -E "5433|8000|8080|6379"
```

Варианты:
- `8000` — убить локальный `uvicorn`: `pkill -f "uvicorn app.main:app"`
- `8080` — остановить другой веб-сервер или поменять порт в `docker-compose.yml`
- `5433` — остановить локальный Postgres: `sudo systemctl stop postgresql`
- `6379` — убрать `ports` у Redis в `docker-compose.yml` (он и так не нужен снаружи)

### Бэк в compose падает на старте

```bash
docker compose logs backend --tail 50
```

Частые причины:
- `postgres` не успел стать healthy — но у нас `depends_on: service_healthy`,
  так что должно ждать. Если падает по connection — проверьте `healthcheck`
  в compose.
- `alembic upgrade` падает — миграции битые, смотрите трейсбек.
- `entrypoint.sh: not found` — CRLF-переносы в файле. Лечится:
  `sed -i 's/\r$//' backend/entrypoint.sh`.

### `alembic current` падает `connection refused`

`.env` смотрит на несуществующий Postgres. Для локальной разработки должен
быть `localhost:5433` (контейнерный Postgres), не `localhost:5432`
(системный).

### Cookie не ставится

- Через `http://localhost:8080` — должно работать (same-origin).
- Через `http://localhost:8000` напрямую — нужен `credentials: 'include'`
  и CORS разрешён для origin фронта (`CORS_ORIGINS` в `.env`).
- `Secure=false` — только для локальной разработки. Для HTTPS-прода
  поменять на `true`.

---

## Что сделано / что осталось

### Сделано (stage 2)

- Auth: регистрация, вход, выход, `/me` с cookie
- Заявки: создание, список, детали, accept (SUCCESS → AWAITING_DISBURSEMENT)
- Админ: список с фильтром по датам, детали, complete
- История статусов и платёжные поручения
- Mock-скоринг (детерминированный)
- Docker-стек: compose, entrypoint с миграциями и seed, nginx-прокси

### В работе

- `SCORING_MODE=mock|ml` + прокси `/api/companies/*` — ждём ML
- Реальный ML-скоринг и `/score` (ветка `ml/scoring`)
- `OFFER`-статус и `accept-offer` — контракт в `docs/api.md`, реализация
  вместе с ML
- `INFO`-статус (дозапрос документов) — этап 2

### Технический долг

- `RedisSessionStore` — заготовка в `session_store.py`, сейчас сессии в Postgres
- `RedisCache` — заготовка, кэш не подключён
- Реальная ролевая модель для админов (сейчас флаг `is_admin`)
- Аудит-лог действий администратора
```
