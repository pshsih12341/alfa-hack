# ML-сервис скоринга. Сборка из папки ml/: docker build -t alfa-ml .
# В образ входят только зависимости сервиса: без генератора выборок, обучения и тестов.

FROM python:3.12.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /app
# Сначала только зависимости — этот слой кешируется, пока не меняется uv.lock.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY config ./config
COPY src ./src
RUN uv sync --frozen --no-default-groups

FROM python:3.12.12-slim
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=build /app /app
EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=2)"

CMD ["uvicorn", "alfa_ml.service.app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
