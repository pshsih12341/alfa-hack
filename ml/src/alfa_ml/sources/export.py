"""Выгрузка среза синтетики в базы-моки: в любую БД через SQLAlchemy или init-файлом для PostgreSQL."""
import datetime as dt
import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import Date, Engine, Integer, Table, create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable, SetTableComment

from alfa_ml.sources.schema import TURNOVER_COLUMNS, metadata


def sqlite_engine(path: Path) -> Engine:
    """SQLite через SQLAlchemy. Путь передаётся напрямую, а не в URL: в нём может быть кириллица."""
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(path))


def source_tables(batch) -> dict[str, pd.DataFrame]:
    """Таблицы схемы из выборки генератора. batch — объект с таблицами Batch."""
    comp = batch.companies
    org_inn = comp[["application_id", "inn"]].rename(columns={"inn": "org_inn"})
    as_of = comp["application_id"].map(batch.applications.set_index("application_id")["application_date"])
    roles = batch.persons.merge(org_inn, on="application_id")
    with_fns = comp["fns_revenue"].notna()
    alfa = comp[comp["is_alfa_client"]]
    turnover = batch.monthly.merge(org_inn, on="application_id")
    turnover = turnover[turnover["application_id"].isin(alfa["application_id"])]
    return {
        "egr_organizations": comp[["inn", "ogrn", "legal_form", "name", "registration_date", "status", "okved_code"]],
        "egr_roles": pd.DataFrame({
            "org_inn": roles["org_inn"], "person_inn": roles["inn"], "person_name": roles["name"],
            "is_director": roles["is_director"], "share": roles["share"],
        }),
        "egr_person_history": batch.person_history,
        "efrsb_cases": batch.bankruptcy_cases,
        "rfm_entries": batch.rfm_entries,
        "bki_subjects": batch.bki_subjects.rename(columns={"subject_inn": "inn"}),
        "bki_inquiries": batch.bki_inquiries.rename(columns={"subject_inn": "inn"}),
        "bki_loans": batch.bki_loans.rename(columns={"subject_inn": "borrower_inn"}),
        "fns_ens": pd.DataFrame({"inn": comp["inn"], "debt": comp["ens_debt"], "as_of_date": as_of}),
        "fns_financials": pd.DataFrame({
            "inn": comp.loc[with_fns, "inn"], "year": as_of[with_fns].dt.year - 1,
            "revenue": comp.loc[with_fns, "fns_revenue"],
        }),
        # Счёт в Альфе открыт при регистрации бизнеса: обороты есть за все месяцы его работы.
        "alfa_clients": pd.DataFrame({"inn": alfa["inn"], "client_since": alfa["registration_date"]}),
        "alfa_turnover": turnover[["org_inn", "month", *TURNOVER_COLUMNS]].rename(columns={"org_inn": "inn"}),
    }


def _records(table: Table, frame: pd.DataFrame) -> list[dict]:
    """Строки для вставки: пропуски — None, даты — date, значения — обычные типы Python."""
    columns = {}
    for column in table.columns:
        values = frame[column.name]
        if isinstance(column.type, Date):
            values = pd.to_datetime(values).dt.date
        # Список собирается без pandas: иначе None снова превратится в NaN.
        items = [v if present else None for v, present in zip(values.astype(object).tolist(), values.notna())]
        if isinstance(column.type, Integer):
            # Целые с пропусками pandas хранит как 45.0, а COPY в INTEGER такое не примет.
            items = [None if v is None else int(v) for v in items]
        columns[column.name] = items
    return [dict(zip(columns, row)) for row in zip(*columns.values())]


def export_database(batch, engine: Engine) -> None:
    """Пересоздаёт таблицы схемы в базе engine и заполняет их выборкой."""
    tables = source_tables(batch)
    with engine.begin() as conn:
        metadata.drop_all(conn)
        metadata.create_all(conn)
        for table in metadata.sorted_tables:
            rows = _records(table, tables[table.name])
            if rows:
                conn.execute(table.insert(), rows)


def _copy_value(value) -> str:
    """Значение в текстовом формате COPY: NULL — \\N, спецсимволы экранируются."""
    if value is None:
        return r"\N"
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value)
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def write_postgres_init(batch, path: Path, database: str = "mocks", owner: str = "credit_kiosk") -> None:
    """SQL-файл для psql: создаёт базу database, схему и загружает данные через COPY.

    Можно запускать повторно и от суперпользователя (sudo -u postgres psql -f …), и как
    init-скрипт контейнера: база и таблицы принадлежат owner, старые таблицы пересоздаются.
    """
    dialect = postgresql.dialect()
    tables = source_tables(batch)
    lines = [
        "-- Базы-моки источников для кредитного конвейера. Сгенерировано: python -m alfa_ml.synth.",
        "-- Не редактировать вручную: данные пересоздаются генератором с тем же seed.",
        "\\set ON_ERROR_STOP on",
        f"SELECT 'CREATE DATABASE {database} OWNER {owner}'",
        f"WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{database}')\\gexec",
        f"ALTER DATABASE {database} OWNER TO {owner};",
        f"\\connect {database}",
        f"SET ROLE {owner};",
        *[f"DROP TABLE IF EXISTS {table.name} CASCADE;" for table in reversed(metadata.sorted_tables)],
        "",
    ]
    for table in metadata.sorted_tables:
        lines.append(f"{str(CreateTable(table).compile(dialect=dialect)).strip()};")
        lines += [f"{CreateIndex(index).compile(dialect=dialect)};" for index in table.indexes]
        if table.comment:
            lines.append(f"{SetTableComment(table).compile(dialect=dialect)};")
        lines.append("")
    for table in metadata.sorted_tables:
        names = [column.name for column in table.columns]
        lines.append(f"COPY {table.name} ({', '.join(names)}) FROM stdin;")
        lines += ["\t".join(_copy_value(row[name]) for name in names) for row in _records(table, tables[table.name])]
        lines += ["\\.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
