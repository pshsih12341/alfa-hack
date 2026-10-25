from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.features import statements
from alfa_ml.features.build import (MODEL1_FEATURES, MODEL2_FEATURES, model1_features, model2_features,
                                    okved_group, profile, stage1_dscr)
from alfa_ml.finance import annuity_payment
from alfa_ml.synth.datasets import Context, Segment, build_sample
from alfa_ml.synth.ids import IdCounter, InnFactory

SCORING = load_config("scoring")
GROUPS = list(SCORING["okved_groups"])
FLAT = pd.DataFrame(1.0, index=GROUPS, columns=range(1, 13))
APP_DATE = pd.Timestamp("2026-11-01")


def _months(app_id, inflows, outflow_share=0.6, top_share=0.3):
    """Выписка: последние len(inflows) месяцев до APP_DATE, поступления только от покупателей."""
    months = pd.date_range(end=APP_DATE - pd.DateOffset(months=1), periods=len(inflows), freq="MS")
    zeros = np.zeros(len(inflows))
    inflows = np.asarray(inflows, dtype=float)
    return pd.DataFrame({
        "application_id": app_id, "month": months,
        "inflow_customers": inflows, "inflow_acquiring": zeros, "inflow_cash": zeros,
        "outflow_suppliers": inflows * outflow_share, "outflow_salary": zeros, "outflow_rent": zeros,
        "outflow_taxes": zeros, "outflow_other_debt": zeros, "top_customer_inflow": inflows * top_share,
    })


def _data():
    """Пять заявок с известными ответами."""
    apps = pd.DataFrame({
        "application_id": [1, 2, 3, 4, 5],
        "application_date": APP_DATE,
        "requested_amount": 1_000_000.0,
        "term_months": 12,
        "declared_revenue": [5e6, 5e6, 3e6, 4e6, 6e6],
        "refinance_loan_ids": [[10], [], [], [], []],
        "purpose": ["refinancing", "working_capital", "equipment", "current_expenses", "real_estate"],
        "has_collateral": [False, False, True, False, True],
    })
    companies = pd.DataFrame({
        "application_id": [1, 2, 3, 4, 5],
        "legal_form": ["ooo", "ooo", "ip", "ip", "ooo"],
        "registration_date": APP_DATE - pd.to_timedelta([3650, 3650, 700, 200, 120], unit="D"),
        "okved_code": ["62.01", "47.11", "47.11", "56.10", "41.20"],
        "is_alfa_client": [True, False, False, True, True],
        "fns_revenue": [2e6, 2e6, np.nan, np.nan, 2.5e6],
        "ens_debt": [0.0, 15000.0, 9000.0, 0.0, 0.0],
    })
    persons = pd.DataFrame({
        "application_id": [1, 2, 3, 4, 5], "inn": ["p1", "p2", "p3", "p4", "p5"],
        "is_director": True, "share": [1.0, 1.0, 1.0, 1.0, 1.0],
        "track_record": ["ok", "first", "problem", "first", "ok"],
    })
    subjects = pd.DataFrame({
        "application_id": [1, 2, 3, 4, 5], "subject_inn": ["c1", "c2", "p3", "p4", "c5"],
        "is_borrower": True, "has_history": [True, True, False, True, True],
        "max_dpd_24m": [0.0, 45.0, np.nan, 10.0, 0.0], "inquiries_90d": [0, 2, 1, 0, 3],
    })
    loans = pd.DataFrame({
        "application_id": [1, 1, 3], "loan_id": [10, 11, 12], "subject_inn": ["c1", "c1", "p3"],
        "is_business": [True, True, False], "balance": [500_000.0, 300_000.0, 2_000_000.0],
        "monthly_payment": [10_000.0, 7_000.0, 25_000.0],
    })
    monthly = pd.concat([
        _months(1, [100_000.0] * 12),
        _months(4, [80_000.0] * 5),
        _months(5, [90_000.0] * 2),
    ], ignore_index=True)
    return SimpleNamespace(applications=apps, companies=companies, persons=persons, bki_subjects=subjects,
                           bki_loans=loans, monthly=monthly)


@pytest.fixture(scope="module")
def prof():
    return profile(_data(), SCORING, FLAT)


@pytest.mark.parametrize(("code", "group"), [("47.11", "trade"), ("62.01", "it_services"), ("70.22", "it_services"),
                                             ("68.20", "other"), ("01.11", "agriculture"), ("56.10", "food_service")])
def test_okved_group(code, group):
    assert okved_group(pd.Series([code]), SCORING["okved_groups"]).iloc[0] == group


def test_revenue_priority(prof):
    # 1: клиент Альфы с годом выписок; 2: ООО не из Альфы — ФНС; 3: ИП не из Альфы — анкета;
    # 4: клиент Альфы с 5 месяцами; 5: клиент Альфы, но 2 месяца — мало, берём ФНС.
    assert prof["revenue_source"].tolist() == ["alfa_full", "fns", "declared", "alfa_partial", "fns"]
    assert prof["revenue1"].tolist() == pytest.approx([1.2e6, 2e6, 3e6, 80_000 * 12, 2.5e6])


def test_stage1_flow_subtracts_living_cost_for_ip(prof):
    # ИП, торговля: 3 млн / 12 × маржа 6% × 0.8 − 30 тыс. на жизнь.
    assert prof.loc[3, "flow1"] == pytest.approx(3e6 / 12 * 0.06 * 0.8 - 30_000)
    assert prof.loc[2, "flow1"] == pytest.approx(2e6 / 12 * 0.06 * 0.8)


def test_refinanced_loan_excluded(prof):
    assert prof.loc[1, "business_debt"] == 300_000
    assert prof.loc[1, "existing_payments"] == 7_000
    # Личные кредиты ИП не входят в долг, но входят в платежи.
    assert prof.loc[3, "business_debt"] == 0 and prof.loc[3, "existing_payments"] == 25_000


def test_model2_only_with_enough_statements(prof):
    assert prof["revenue2"].notna().tolist() == [True, False, False, True, False]
    # Поток 100 тыс. − 60 тыс. каждый месяц: консервативный поток 40 тыс.
    assert prof.loc[1, "flow2"] == pytest.approx(40_000)
    assert prof.loc[4, "flow2"] == pytest.approx(80_000 * 0.4 - 30_000)


def test_dscr_uses_payment_at_rate_and_existing_loans(prof):
    x2 = model2_features(prof, prof.shape[0] * [1_000_000.0], 12, 0.18)
    expected = 40_000 / (annuity_payment(1_000_000, 0.18, 12) + 7_000)
    assert x2.loc[1, "dscr"] == pytest.approx(expected)
    assert stage1_dscr(prof, 1_000_000.0, 12, 0.18).loc[1] == pytest.approx(
        prof.loc[1, "flow1"] / (annuity_payment(1_000_000, 0.18, 12) + 7_000))


def test_statement_features(prof):
    assert prof.loc[1, "top_customer_share"] == pytest.approx(0.3)
    assert prof.loc[1, "fcf_volatility"] == pytest.approx(0.0)
    assert prof.loc[1, "turnover_trend"] == pytest.approx(1.0)
    assert np.isnan(prof.loc[4, "turnover_trend"])  # 5 месяцев — тренд не считается


def test_trend_removes_seasonality():
    # Чисто сезонный бизнес без роста: после снятия сезонности тренд равен 1.
    pattern = np.array([0.6, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.4, 1.6, 1.4, 1.0, 0.9])
    months = pd.date_range("2025-01-01", periods=12, freq="MS")
    monthly = pd.concat([_months(i, 100_000 * pattern) for i in (1, 2)], ignore_index=True)
    monthly["month"] = np.tile(months, 2)
    groups = pd.Series(["agriculture", "agriculture"], index=[1, 2])
    index = statements.seasonal_index(monthly, groups, GROUPS)
    assert index.loc["agriculture"].to_numpy() == pytest.approx(pattern / pattern.mean())
    assert index.loc["trade"].to_numpy() == pytest.approx(np.ones(12))
    trend = statements.turnover_trend(monthly, groups, index)
    assert trend.to_numpy() == pytest.approx([1.0, 1.0])
    raw = statements.turnover_trend(monthly, groups, FLAT)
    assert raw.iloc[0] > 1.1  # без поправки осенний урожай выглядел бы ростом


def test_model1_matrix(prof):
    x1 = model1_features(prof, [1_000_000.0] * 5)
    assert list(x1.columns) == MODEL1_FEATURES
    assert x1.loc[2, "loan_to_revenue"] == pytest.approx(0.5)
    assert x1["has_tax_debt"].tolist() == [0, 1, 0, 0, 0]  # 9 тыс. — ниже порога 10 тыс.
    assert np.isnan(x1.loc[3, "max_dpd_24m"])  # истории нет — пропуск, а не 0
    assert x1.loc[3, "purpose"] == "equipment" and x1["has_collateral"].tolist() == [0, 0, 1, 0, 1]


@pytest.fixture(scope="module")
def generated():
    gen = load_config("generator")
    ctx = Context(gen, SCORING, InnFactory(np.random.default_rng(11)), IdCounter(), IdCounter())
    batch, _ = build_sample([Segment(2000, gen)], ("2024-01", "2024-12"), ctx, np.random.SeedSequence(11))
    groups = okved_group(batch.companies.set_index("application_id")["okved_code"], SCORING["okved_groups"])
    seasonality = statements.seasonal_index(batch.monthly, groups, GROUPS)
    prof = profile(batch, SCORING, seasonality)
    apps = batch.applications.set_index("application_id")
    rate = batch.labels.set_index("application_id")["rate"]
    x1 = model1_features(prof, apps["requested_amount"])
    x2 = model2_features(prof, apps["requested_amount"], apps["term_months"], rate)
    return batch, prof, x1, x2


def test_generated_features_are_finite_and_complete(generated):
    _, prof, x1, x2 = generated
    numeric = [c for c in MODEL2_FEATURES if x2[c].dtype.kind == "f"]
    assert not np.isinf(x1.select_dtypes("number").to_numpy()).any()
    assert not np.isinf(x2[numeric].to_numpy(dtype=float)).any()
    # В модели 1 пропуски допустимы только в просрочке: «нет кредитной истории».
    assert x1.drop(columns="max_dpd_24m").notna().all().all()
    # Модель 2 не считается без 3 месяцев выписок, тренд — без 12.
    short = prof["statement_months"] < 3
    assert x2.loc[short, "dscr"].isna().all() and x2.loc[~short, "dscr"].notna().all()
    assert x2.loc[prof["statement_months"] < 12, "turnover_trend"].isna().all()


def test_generated_revenue_sources(generated):
    batch, prof, _, _ = generated
    shares = prof["revenue_source"].value_counts(normalize=True)
    assert set(shares.index) <= {"alfa_full", "alfa_partial", "fns", "declared"}
    ip = prof["legal_form"] == "ip"
    assert (prof.loc[ip, "revenue_source"] != "fns").all()  # у ИП нет открытых данных ФНС
