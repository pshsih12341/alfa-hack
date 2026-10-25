"""Сквозная проверка: срез выгружается в базу и читается обратно по ИНН в те же данные.

SQLite проверяется всегда. PostgreSQL — если задан ALFA_ML_TEST_POSTGRES_URL с отдельной
одноразовой базой (таблицы в ней пересоздаются), например:
postgresql+psycopg://postgres:postgres@localhost:55432/mocks_test
"""
import os
import re

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

from alfa_ml.config import load_config
from alfa_ml.inn import is_valid_ogrn
from alfa_ml.sources.export import export_database, source_tables, sqlite_engine, write_postgres_init
from alfa_ml.sources.read import read_sources
from alfa_ml.sources.schema import TURNOVER_COLUMNS, metadata
from alfa_ml.synth.datasets import Context, Segment, build_sample
from alfa_ml.synth.ids import IdCounter, InnFactory

AS_OF = "2026-11-01"
POSTGRES_URL = os.environ.get("ALFA_ML_TEST_POSTGRES_URL")


@pytest.fixture(scope="module")
def batch():
    gen, scoring = load_config("generator"), load_config("scoring")
    ctx = Context(gen, scoring, InnFactory(np.random.default_rng(3)), IdCounter(), IdCounter())
    return build_sample([Segment(300, gen)], (AS_OF, AS_OF), ctx, np.random.SeedSequence(3))[0]


@pytest.fixture(scope="module", params=[
    "sqlite",
    pytest.param("postgres", marks=pytest.mark.skipif(not POSTGRES_URL, reason="ALFA_ML_TEST_POSTGRES_URL не задан")),
])
def roundtrip(request, batch, tmp_path_factory):
    if request.param == "sqlite":
        engine = sqlite_engine(tmp_path_factory.mktemp("mocks") / "mocks.sqlite")
    else:
        engine = create_engine(POSTGRES_URL)
    export_database(batch, engine)
    with engine.connect() as conn:
        parts = [read_sources(conn, inn, AS_OF, application_id=app)
                 for app, inn in zip(batch.companies["application_id"], batch.companies["inn"])]
        missing = read_sources(conn, "0000000000", AS_OF)
    engine.dispose()
    read = {name: pd.concat([getattr(p, name) for p in parts], ignore_index=True)
            for name in ("companies", "persons", "bki_subjects", "bki_loans", "monthly")}
    return read, missing


def _sorted(frame, keys):
    return frame.sort_values(keys).reset_index(drop=True)


def test_unknown_inn_returns_none(roundtrip):
    assert roundtrip[1] is None


def test_companies_match(batch, roundtrip):
    read, _ = roundtrip
    pd.testing.assert_frame_equal(_sorted(read["companies"], ["application_id"]),
                                  _sorted(batch.companies, ["application_id"]), check_dtype=False)


def test_persons_match(batch, roundtrip):
    read, _ = roundtrip
    got = _sorted(read["persons"], ["application_id", "inn"])
    expected = _sorted(batch.persons, ["application_id", "inn"])
    for col in ("inn", "name", "is_director", "in_rfm_list"):
        assert (got[col].to_numpy() == expected[col].to_numpy()).all(), col
    assert np.allclose(got["share"], expected["share"])
    assert (pd.to_datetime(got["bankruptcy_end_date"]).fillna(pd.Timestamp(0))
            == pd.to_datetime(expected["bankruptcy_end_date"]).fillna(pd.Timestamp(0))).all()
    # Опыт, выведенный из истории в ЕГРЮЛ и ЕФРСБ, совпадает со сгенерированным.
    # Исключение — заявки со свежим банкротством: их отсекает стоп-правило.
    clean = expected["application_id"].isin(batch.labels.loc[batch.labels["heuristic_reason"] == "", "application_id"])
    assert (got.loc[clean, "track_record"] == expected.loc[clean, "track_record"]).all()


def test_bki_match(batch, roundtrip):
    read, _ = roundtrip
    keys = ["application_id", "subject_inn"]
    got, expected = _sorted(read["bki_subjects"], keys), _sorted(batch.bki_subjects, keys)
    for col in ("subject_inn", "subject_type", "is_borrower", "has_history", "inquiries_90d"):
        assert (got[col].to_numpy() == expected[col].to_numpy()).all(), col
    assert np.array_equal(got["max_dpd_24m"].to_numpy(), expected["max_dpd_24m"].to_numpy(), equal_nan=True)
    pd.testing.assert_frame_equal(_sorted(read["bki_loans"], ["loan_id"]), _sorted(batch.bki_loans, ["loan_id"]),
                                  check_dtype=False)


def test_turnover_only_for_alfa_clients(batch, roundtrip):
    read, _ = roundtrip
    clients = batch.companies.loc[batch.companies["is_alfa_client"], "application_id"]
    expected = _sorted(batch.monthly[batch.monthly["application_id"].isin(clients)], ["application_id", "month"])
    pd.testing.assert_frame_equal(_sorted(read["monthly"], ["application_id", "month"]), expected, check_dtype=False)


def test_generator_turnover_columns_match_schema(batch):
    assert [c for c in batch.monthly.columns if c not in ("application_id", "month")] == TURNOVER_COLUMNS


def test_ogrn_valid_and_unique(batch):
    companies = batch.companies
    assert companies["ogrn"].map(is_valid_ogrn).all()
    assert companies["ogrn"].is_unique
    lengths = companies["ogrn"].str.len()
    assert (lengths[companies["legal_form"] == "ip"] == 15).all() and (lengths[companies["legal_form"] == "ooo"] == 13).all()


def test_postgres_init_file(batch, tmp_path):
    path = tmp_path / "mocks_postgres.sql"
    write_postgres_init(batch, path)
    text = path.read_text(encoding="utf-8")
    assert text.count("CREATE TABLE") == len(metadata.tables)
    assert "NUMERIC(15, 2)" in text and "DATE" in text and "BOOLEAN" in text
    # В каждом блоке COPY столько строк, сколько в таблице, и в каждой строке столько полей, сколько колонок.
    tables = source_tables(batch)
    for match in re.finditer(r"^COPY (\w+) \(([^)]*)\) FROM stdin;\n(.*?)^\\\.$", text, flags=re.M | re.S):
        name, columns, body = match.group(1), match.group(2).split(", "), match.group(3)
        rows = body.splitlines()
        assert len(rows) == len(tables[name]), name
        assert all(len(row.split("\t")) == len(columns) for row in rows), name
    # Пропуски — только \N: «nan» PostgreSQL не примет ни в числовую, ни в целую колонку.
    assert not re.search(r"(^|\t)(nan|NaT|None)(\t|$)", text, flags=re.M)
    assert not re.search(r"(^|\t)\d+\.0(\t|$)", text.split("COPY bki_subjects", 1)[1].split("\\.", 1)[0], flags=re.M)
