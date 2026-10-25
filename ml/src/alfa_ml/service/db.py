"""Подключение к базам-мокам."""
import datetime as dt
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, func, select

from alfa_ml.sources import schema
from alfa_ml.sources.export import sqlite_engine


def make_engine(url: str) -> Engine:
    """PostgreSQL через psycopg 3 или файл SQLite.

    postgresql:// и postgres:// без драйвера приводятся к postgresql+psycopg://.
    Пул маленький: сервис рассчитан на сервер с 1 ГБ и заявки по одной.
    """
    if url.startswith("sqlite:///"):
        return sqlite_engine(Path(url.removeprefix("sqlite:///")))
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url.removeprefix(prefix)
    return create_engine(url, pool_size=2, max_overflow=3, pool_pre_ping=True)


def snapshot_date(conn: Connection) -> dt.date | None:
    """Дата среза моков — по данным ФНС, они выгружаются на эту дату для всех компаний."""
    value = conn.execute(select(func.max(schema.fns_ens.c.as_of_date))).scalar()
    return dt.date.fromisoformat(value) if isinstance(value, str) else value
