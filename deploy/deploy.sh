#!/usr/bin/env bash
# Деплой на сервер (Ubuntu/Debian, от root). Запуск из корня проекта на сервере:
#   bash deploy/deploy.sh          — собрать и запустить (повторный запуск обновляет)
#   bash deploy/deploy.sh --seed   — ещё и создать демо-клиентов; УДАЛЯЕТ все прежние заявки и клиентов
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
SEED=false
[ "${1:-}" = "--seed" ] && SEED=true

step() { printf '\n== %s\n' "$*"; }

step "Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker не найден — ставлю официальным скриптом get.docker.com"
  curl -fsSL https://get.docker.com | sh
fi
version=$(docker compose version --short | sed 's/^v//')
if [ "$(printf '%s\n' 2.24.4 "$version" | sort -V | head -1)" != "2.24.4" ]; then
  echo "Нужен Docker Compose 2.24.4 или новее, сейчас $version: обновите docker-compose-plugin"
  exit 1
fi
echo "Docker Compose $version"

step "Память"
mem_mb=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
echo "ОЗУ: ${mem_mb} МБ"
if [ "$mem_mb" -lt 2048 ] && [ -z "$(swapon --show --noheadings)" ]; then
  # Сборка фронта (npm ci + vite) на 1 ГБ без swap может упасть по памяти.
  echo "Swap нет — создаю /swapfile на 2 ГБ"
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

step "Старые стеки на портах 80 и 443"
ours=$("${COMPOSE[@]}" config | awk '/^name:/ {print $2; exit}')
for port in 80 443; do
  for id in $(docker ps -q --filter "publish=$port"); do
    project=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
    if [ -z "$project" ]; then
      echo "Порт $port занят контейнером $(docker inspect -f '{{.Name}}' "$id") не из compose — остановите его вручную"
      exit 1
    fi
    if [ "$project" != "$ours" ]; then
      echo "Останавливаю стек $project (тома с данными сохраняются)"
      docker compose -p "$project" down
    fi
  done
done

step "Сборка образов по одному — меньше пиковая память"
for service in ml backend frontend; do
  "${COMPOSE[@]}" build "$service"
done

step "Запуск"
"${COMPOSE[@]}" up -d --remove-orphans
"${COMPOSE[@]}" rm -s -f redis >/dev/null 2>&1 || true

step "Ожидание бэкенда и ML"
ready=false
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" >/dev/null 2>&1 \
    && "${COMPOSE[@]}" exec -T ml python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 3
done
if ! $ready; then
  echo "Бэкенд или ML не ответили за 3 минуты — логи:"
  "${COMPOSE[@]}" logs --tail 50 backend ml
  exit 1
fi
"${COMPOSE[@]}" exec -T ml python -c "import urllib.request as u; print(u.urlopen('http://localhost:8001/health').read().decode())"

step "Администратор и демо-клиенты"
"${COMPOSE[@]}" exec -T backend python scripts/seed_admin.py +79990009999
if $SEED; then
  "${COMPOSE[@]}" exec -T backend python scripts/seed_demo.py
fi

step "Сервисы и опубликованные порты"
"${COMPOSE[@]}" ps
echo
echo "Слушают не только localhost (наружу должны смотреть только 22, 80, 443):"
ss -tlnp | awk 'NR == 1 || ($4 !~ /^127\./ && $4 !~ /^\[::1\]/)'

echo
echo "Готово: https://misisitmo.itatmisis.ru"
