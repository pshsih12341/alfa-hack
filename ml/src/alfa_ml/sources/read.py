"""Чтение данных по ИНН из баз-моков в те же таблицы, что строит генератор. Этим путём идёт скоринг.

Работает через SQLAlchemy одинаково с PostgreSQL и SQLite.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import Connection, Date, Table, select

from alfa_ml.sources import schema

BAD_OUTCOMES = ["excluded_by_fns", "bankruptcy", "closed_with_debts"]


@dataclass
class SourceData:
    """Данные одной заявки; у всех таблиц application_id — номер заявки."""
    companies: pd.DataFrame        # одна строка
    persons: pd.DataFrame
    bki_subjects: pd.DataFrame
    bki_loans: pd.DataFrame
    monthly: pd.DataFrame          # обороты в Альфе за полные месяцы до заявки; пусто — не клиент
    bankruptcy_cases: pd.DataFrame
    rfm_entries: pd.DataFrame


def derive_track_record(person_inns: pd.Series, history: pd.DataFrame, bankruptcies: pd.DataFrame) -> pd.Series:
    """Опыт собственника: problem — бизнес закрыт плохо или было личное банкротство;
    ok — другие бизнесы есть и закрыты нормально или работают; first — других бизнесов нет."""
    bad = set(history.loc[history["outcome"].isin(BAD_OUTCOMES), "person_inn"]) | set(bankruptcies["debtor_inn"])
    known = set(history["person_inn"])
    return person_inns.map(lambda inn: "problem" if inn in bad else "ok" if inn in known else "first")


def read_sources(conn: Connection, inn: str, as_of, application_id: int = 0,
                 inquiries_window_days: int = 90, statement_months: int = 12) -> SourceData | None:
    """Всё, что известно об ИНН на дату as_of. None — организации нет в ЕГРЮЛ/ЕГРИП."""
    as_of = pd.Timestamp(as_of)
    org = _select(conn, schema.egr_organizations, "inn", [inn])
    if org.empty:
        return None
    org = org.iloc[0]
    roles = _select(conn, schema.egr_roles, "org_inn", [inn])
    linked = list(dict.fromkeys([inn, *roles["person_inn"]]))  # у ИП ИНН организации и человека совпадают
    cases = _select(conn, schema.efrsb_cases, "debtor_inn", linked)
    rfm = _select(conn, schema.rfm_entries, "inn", linked)
    history = _select(conn, schema.egr_person_history, "person_inn", list(roles["person_inn"]))
    subjects = _select(conn, schema.bki_subjects, "inn", linked)
    inquiries = _select(conn, schema.bki_inquiries, "inn", linked)
    loans = _select(conn, schema.bki_loans, "borrower_inn", [inn])
    ens = _select(conn, schema.fns_ens, "inn", [inn])
    financials = _select(conn, schema.fns_financials, "inn", [inn])
    revenue = financials.loc[financials["year"] == as_of.year - 1, "revenue"]
    is_client = not _select(conn, schema.alfa_clients, "inn", [inn]).empty

    company_cases = cases[(cases["debtor_type"] == "company") & (cases["status"] == "in_progress")]
    companies = pd.DataFrame([{
        "application_id": application_id,
        "inn": inn,
        "ogrn": org["ogrn"],
        "legal_form": org["legal_form"],
        "name": org["name"],
        "registration_date": pd.Timestamp(org["registration_date"]),
        "status": org["status"],
        "bankruptcy_procedure": bool((company_cases["debtor_inn"] == inn).any()),
        "in_rfm_list": bool(((rfm["inn"] == inn) & (rfm["entity_type"] == "company")).any()),
        "okved_code": org["okved_code"],
        "is_alfa_client": is_client,
        "fns_revenue": float(revenue.iloc[0]) if len(revenue) else np.nan,
        "ens_debt": float(ens["debt"].iloc[0]) if len(ens) else 0.0,
    }])

    completed = cases[(cases["debtor_type"] == "person") & (cases["status"] == "completed")]
    persons = pd.DataFrame({
        "application_id": application_id,
        "inn": roles["person_inn"],
        "name": roles["person_name"],
        "is_director": roles["is_director"].astype(bool),
        "share": roles["share"].astype(float),
    })
    persons["track_record"] = derive_track_record(persons["inn"], history, completed)
    persons["bankruptcy_end_date"] = completed.groupby("debtor_inn")["end_date"].max().reindex(persons["inn"]).to_numpy()
    persons["in_rfm_list"] = persons["inn"].isin(rfm.loc[rfm["entity_type"] == "person", "inn"])

    recent = inquiries[(as_of - inquiries["inquiry_date"]).dt.days < inquiries_window_days]
    bki = pd.DataFrame({"subject_inn": linked}).merge(subjects.rename(columns={"inn": "subject_inn"}),
                                                      on="subject_inn", how="left")
    is_company = (bki["subject_inn"] == inn) & (org["legal_form"] == "ooo")
    bki_subjects = pd.DataFrame({
        "application_id": application_id,
        "subject_inn": bki["subject_inn"],
        "subject_type": np.where(is_company, "company", "person"),
        "is_borrower": bki["subject_inn"] == inn,
        "has_history": bki["has_history"].fillna(False).astype(bool),
        "max_dpd_24m": bki["max_dpd_24m"].astype(float),
        "inquiries_90d": recent.groupby("inn").size().reindex(bki["subject_inn"]).fillna(0).astype(int).to_numpy(),
    })

    bki_loans = pd.DataFrame({
        "application_id": application_id,
        "loan_id": loans["loan_id"].astype("int64"),
        "subject_inn": loans["borrower_inn"],
        "lender": loans["lender"],
        "is_business": loans["is_business"].astype(bool),
        "balance": loans["balance"].astype(float),
        "monthly_payment": loans["monthly_payment"].astype(float),
        "remaining_months": loans["remaining_months"].astype(int),
    })

    month_start = as_of.to_period("M").start_time
    turnover = _select(conn, schema.alfa_turnover, "inn", [inn])
    turnover = turnover[(turnover["month"] >= month_start - pd.DateOffset(months=statement_months))
                        & (turnover["month"] < month_start)]
    monthly = turnover.drop(columns="inn").sort_values("month").reset_index(drop=True)
    monthly.insert(0, "application_id", application_id)

    return SourceData(
        companies=companies,
        persons=persons,
        bki_subjects=bki_subjects,
        bki_loans=bki_loans,
        monthly=monthly,
        bankruptcy_cases=cases.assign(application_id=application_id),
        rfm_entries=rfm.assign(application_id=application_id),
    )


def _select(conn: Connection, table: Table, column: str, values: list) -> pd.DataFrame:
    """Строки таблицы, где column из списка values; колонки-даты — datetime64."""
    frame = pd.read_sql(select(table).where(table.c[column].in_(values)), conn)
    for col in table.columns:
        if isinstance(col.type, Date):
            frame[col.name] = pd.to_datetime(frame[col.name])
    return frame
