# Frontend — React (Vite)

UI кредитного кабинета МСБ. Контракт API — в [`../docs/api.md`](../docs/api.md).

---

## Содержание

1. [Стек](#стек)
2. [Структура](#структура)
3. [Запуск в compose](#запуск-в-compose)
4. [Локальная разработка (dev)](#локальная-разработка-dev)
5. [Интеграция с API](#интеграция-с-api)
6. [Сборка](#сборка)
7. [Переменные окружения](#переменные-окружения)
8. [Troubleshooting](#troubleshooting)

---

## Стек

| Компонент | Версия | Назначение |
|---|---|---|
| React | 18 | UI |
| TypeScript | 5.x | типизация |
| Vite | 5.x | dev-сервер и сборка |
| Node (build) | 24-alpine | сборка в Docker |
| Nginx | 1.27-alpine | раздача статики и прокси `/api` |

---

## Структура

```
frontend/
├── src/                исходники React
├── public/             статика
├── nginx.conf          проксирует /api → backend:8000
├── Dockerfile          multi-stage: node build → nginx
├── package.json
├── vite.config.ts
└── README.md
```

---

## Запуск в compose

Из **корня** репозитория:

```bash
docker compose up --build
```

UI откроется на `http://localhost:8080`.

| Путь | Куда идёт |
|---|---|
| `/` | React-приложение (nginx раздаёт `dist/`) |
| `/api/*` | проксируется на `backend:8000` (same-origin) |

Same-origin значит: cookie `ck_session` отправляются автоматически, CORS
не участвует.

---

## Локальная разработка (dev)

```bash
cd frontend
npm install
npm run dev
```

Vite поднимется на `http://localhost:5173`.

### `vite.config.ts`

Прокси на бэк — обязателен, иначе cookie не будут same-origin:

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
```

**Требует запущенного бэка** на `http://localhost:8000`
(см. [`../backend/README.md`](../backend/README.md) или
`docker compose up -d postgres redis` + `uvicorn`).

---

## Интеграция с API

Полный контракт — [`../docs/api.md`](../docs/api.md).

### Cookie auth

| Свойство | Значение |
|---|---|
| Имя | `ck_session` |
| Устанавливается | на `POST /api/users/reg` и `POST /api/users/login` |
| Удаляется | на `POST /api/users/logout` |
| HTTP-only | да |
| SameSite | `Lax` |
| Max-Age | 30 дней |

Через nginx-прокси — same-origin, `fetch` шлёт cookie автоматически.

Прямые запросы на `:8000` — нужен `credentials: 'include'` + CORS
разрешён для `:5173`, `:3000`, `:8080`.

### Типы из OpenAPI

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

Запускать при старте бэка; перегенерировать при изменении контракта.

### Пример запроса

```ts
const res = await fetch('/api/users/reg', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    phoneNumber: '79991234567',
    inn: '7707083893',
    creditSum: 3000000,
    purpose: 'equipment',
    revenueLast12m: 12000000,
    bkiConsent: true,
  }),
});

if (res.status === 201) {
  const { clientId, applicationId } = await res.json();
  // заявка создана, скоринг идёт в фоне
}
```

### Polling статуса заявки

После `reg` и `POST /api/applications` заявка в `PRESCORING`.
Mock-скоринг переведёт её в `SUCCESS` / `REJECTED` за ~5 секунд.

```ts
async function pollApplication(id: string) {
  for (let i = 0; i < 30; i++) {
    const res = await fetch(`/api/applications/${id}`, {
      credentials: 'include',
    });
    const app = await res.json();

    if (app.status !== 'PRESCORING' && app.status !== 'SCORING') {
      return app;
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error('Скоринг занимает дольше обычного');
}
```

### Статусы

Полный список — в `docs/api.md`, раздел «Статусы заявки». Кратко:

- `PRESCORING` — в очереди
- `SUCCESS` — одобрено, можно `POST /api/applications/{id}/accept`
- `REJECTED` — отказ
- `AWAITING_DISBURSEMENT` — условия приняты, ждём подтверждения банка
- `COMPLETED` — исполнено

---

## Сборка

Production-сборка в образ:

```bash
docker compose build frontend
```

Локально:

```bash
npm run build       # dist/
npm run preview     # проверить dist
```

`Dockerfile` — multi-stage:

1. `node:24-alpine` собирает `dist/` (`npm ci && npm run build`)
2. `nginx:1.27-alpine` раздаёт `dist/` + `nginx.conf` (прокси `/api`)

---

## Переменные окружения

Vite читает `.env`, `.env.local` и т.д.

Сейчас **переменных нет** — все запросы относительные (`/api/...`), поэтому
работают и в dev (через прокси), и в compose (через nginx).

Если понадобится абсолютный URL бэка (например, фронт на отдельном домене) —
добавить `VITE_API_BASE_URL` и подставить в fetch.

---

## Troubleshooting

### `docker compose build frontend` падает на `npm ci`

| Причина | Решение |
|---|---|
| Нет `package-lock.json` | `npm install` локально, закоммитить lock-файл |
| Устаревший lock | `npm install` локально, закоммитить обновлённый lock |

Менее воспроизводимо, но быстро: заменить `npm ci` на `npm install`
в `Dockerfile`.

### `Failed to connect to localhost:8000` в dev

Бэк не запущен. Из корня:

```bash
docker compose up -d postgres redis
cd backend && uvicorn app.main:app --port 8000
```

Или поднять весь стек:

```bash
docker compose up --build
```

### Cookie не ставятся через `:8080`

Проверить по порядку:

1. Запрос идёт через **nginx-прокси** (`/api/...`), а не напрямую на `:8000`.
2. В `nginx.conf` — `proxy_pass http://backend:8000;` **без** завершающего
   `/` (иначе путь обрежется).
3. В DevTools → Application → Cookies должна быть `ck_session` на `localhost:8080`.
4. Запрос с `credentials: 'include'` (для same-origin не обязательно, но
   не вредит).

### Пустая страница после `npm run build`

Проверить, что `dist/` собран и `nginx.conf` указывает на правильный `root`:

```nginx
root /usr/share/nginx/html;
index index.html;
```

И что `Dockerfile` копирует `dist/`:

```dockerfile
COPY --from=build /app/dist /usr/share/nginx/html
```

Для CRA путь `/app/build`, для Vite — `/app/dist`.

### `404` на `/api/...` через `:8080`

`nginx.conf` не подхватился. Проверить:

```bash
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

Там должен быть `location /api/ { proxy_pass http://backend:8000; }`.

---

## Ссылки

- Контракт API: [`../docs/api.md`](../docs/api.md)
- Корневой README: [`../README.md`](../README.md)
- Backend README: [`../backend/README.md`](../backend/README.md)
- Swagger: `http://localhost:8000/docs`