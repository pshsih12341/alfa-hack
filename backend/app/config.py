from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite:///./credit_kiosk.db"
    COOKIE_NAME: str = "ck_session"
    COOKIE_MAX_AGE: int = 60 * 60 * 24 * 30  # 30 дней
    COOKIE_SECURE: bool = False
    COOKIE_SAME_SITE: Literal["lax", "strict", "none"] = "lax"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"


settings = Settings()
