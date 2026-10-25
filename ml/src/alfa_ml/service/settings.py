"""Настройки сервиса из переменных окружения."""
import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "postgresql://credit_kiosk:credit_kiosk@localhost:5432/mocks"


@dataclass(frozen=True)
class Settings:
    # Базы-моки: postgresql://… (драйвер psycopg подставляется сам) или sqlite:///путь/к/файлу.
    database_url: str = DEFAULT_DATABASE_URL
    # Дата, на которую считаются возраст бизнеса, окна выписок и запросов в БКИ.
    # По умолчанию — дата среза моков из самой базы, а не часы сервера.
    as_of: str | None = None
    # Разрешённые источники для прямых запросов из браузера; по умолчанию CORS закрыт.
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.environ.get("ML_CORS_ORIGINS", "")
        return cls(
            database_url=os.environ.get("ML_DATABASE_URL", DEFAULT_DATABASE_URL),
            as_of=os.environ.get("ML_AS_OF") or None,
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        )
