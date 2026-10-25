"""Логика этапа 1 на заявке, где всё можно посчитать вручную.

ООО, торговля (маржа 6%), выручка 12 млн из анкеты: поток этапа 1 = 1 млн × 6% × 0.8 = 48 тыс.
При DSCR ≥ 1.25 допустимый платёж — 38 400 ₽.
"""
import numpy as np
import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.decision.stage1 import Application, RevenueRequired, decide_stage1, percent, product
from alfa_ml.finance import annuity_payment
from alfa_ml.sources.read import SourceData

SCORING = load_config("scoring")
RULES = load_config("rules")
AS_OF = pd.Timestamp("2026-11-01")
GOOD = lambda x: np.full(len(x), 0.02)  # noqa: E731 — PD 2% на любой сумме


def _source(legal_form="ooo", status="active", fns_revenue=np.nan):
    inn = "7707083893" if legal_form == "ooo" else "500100732259"
    empty_monthly = pd.DataFrame(columns=["application_id", "month", "inflow_customers", "inflow_acquiring",
                                          "inflow_cash", "outflow_suppliers", "outflow_salary", "outflow_rent",
                                          "outflow_taxes", "outflow_other_debt", "top_customer_inflow"])
    return SourceData(
        companies=pd.DataFrame([{
            "application_id": 0, "inn": inn, "ogrn": "1", "legal_form": legal_form, "name": "x",
            "registration_date": AS_OF - pd.DateOffset(years=5), "status": status, "bankruptcy_procedure": False,
            "in_rfm_list": False, "okved_code": "47.11", "is_alfa_client": False, "fns_revenue": fns_revenue,
            "ens_debt": 0.0,
        }]),
        persons=pd.DataFrame([{"application_id": 0, "inn": "500100732259", "name": "y", "is_director": True,
                               "share": 1.0, "track_record": "ok", "bankruptcy_end_date": pd.NaT,
                               "in_rfm_list": False}]),
        bki_subjects=pd.DataFrame([{"application_id": 0, "subject_inn": inn, "subject_type": "company",
                                    "is_borrower": True, "has_history": True, "max_dpd_24m": 0.0,
                                    "inquiries_90d": 0}]),
        bki_loans=pd.DataFrame(columns=["application_id", "loan_id", "subject_inn", "lender", "is_business",
                                        "balance", "monthly_payment", "remaining_months"]).astype(
            {"application_id": int, "loan_id": int, "is_business": bool, "balance": float, "monthly_payment": float}),
        monthly=empty_monthly.astype({"application_id": int, "month": "datetime64[ns]"}),
        bankruptcy_cases=pd.DataFrame(), rfm_entries=pd.DataFrame(),
    )


def _decide(credit_sum, term, predict=GOOD, source=None, revenue=12_000_000):
    app = Application(credit_sum, term, "working_capital", (), revenue)
    return decide_stage1(source or _source(), app, AS_OF, SCORING, RULES, predict_pd=predict)


def test_approved_when_requested_terms_pass():
    decision = _decide(300_000, 12)
    assert decision.decision == "APPROVED"
    assert decision.approved.credit_sum == 300_000 and decision.approved.rate == 0.18
    assert decision.approved.monthly_payment == round(float(annuity_payment(300_000, 0.18, 12)))


def test_offer_like_spec_example():
    # 1.5 млн на 12 мес: платёж ~137.5 тыс. при допустимых 38.4 тыс. — не проходит нигде.
    decision = _decide(1_500_000, 12)
    assert decision.decision == "OFFER"
    assert [(o.credit_sum, o.term_months) for o in decision.offers] == [(400_000, 12), (1_050_000, 36)]
    assert decision.documents_required == ["bankStatements"]


def test_second_offer_is_requested_sum_on_shortest_passing_term():
    decision = _decide(800_000, 12)
    assert [(o.credit_sum, o.term_months) for o in decision.offers] == [(400_000, 12), (800_000, 30)]


def test_max_by_term_bounds():
    decision = _decide(1_500_000, 12)
    maxima = [o.credit_sum if o else 0 for _, o in decision.max_by_term]
    assert [months for months, _ in decision.max_by_term] == SCORING["terms_months"]
    assert maxima == sorted(maxima)  # чем длиннее срок, тем больше проходит
    assert all(m <= 1_500_000 for m in maxima)
    for months, option in decision.max_by_term:
        if option:  # максимальная сумма проходит, следующая ступень — уже нет
            payment = float(annuity_payment(option.credit_sum, option.rate, months))
            assert 48_000 / payment >= 1.25
            assert 48_000 / float(annuity_payment(option.credit_sum + 50_000, option.rate, months)) < 1.25


def test_grey_zone_gets_smaller_sum_without_statements():
    # PD 10% на запрошенной сумме (доля в выручке ≥ 5%), 2% — на меньших.
    def predict(x):
        return np.where(x["loan_to_revenue"] >= 0.05, 0.10, 0.02)
    decision = _decide(1_000_000, 36, predict=predict)
    assert decision.decision == "OFFER"
    assert decision.pd == pytest.approx(0.10)
    assert all(o.credit_sum < 600_000 for o in decision.offers)


def test_info_when_nothing_passes_without_statements():
    decision = _decide(1_000_000, 36, predict=lambda x: np.full(len(x), 0.10))
    assert decision.decision == "INFO" and decision.offers == [] and decision.documents_required == ["bankStatements"]


def test_rejected_above_decline_threshold():
    decision = _decide(1_000_000, 36, predict=lambda x: np.full(len(x), 0.35))
    assert decision.decision == "REJECTED" and decision.stop_rules == []


def test_stop_rule_rejects_before_model():
    decision = _decide(300_000, 12, source=_source(status="liquidating"),
                       predict=lambda x: pytest.fail("модель не должна считаться"))
    assert decision.decision == "REJECTED" and decision.stop_rules == ["inactive_status"]


def test_revenue_required_when_unknown():
    with pytest.raises(RevenueRequired):
        _decide(300_000, 12, source=_source(legal_form="ip"), revenue=None)
    # У ООО с данными ФНС выручку из анкеты можно не передавать.
    assert _decide(300_000, 12, source=_source(fns_revenue=12e6), revenue=None).decision == "APPROVED"


def test_collateral_lowers_rate():
    app = Application(300_000, 12, "equipment", (), 12_000_000, has_collateral=True)
    decision = decide_stage1(_source(), app, AS_OF, SCORING, RULES, predict_pd=GOOD)
    assert decision.decision == "APPROVED" and decision.approved.rate == 0.175
    assert product(app) == "collateral" and "под 17,5% годовых" in decision.client_message
    assert product(Application(300_000, 12, "equipment")) == "no_collateral"


def test_percent_for_client():
    assert percent(0.175) == "17,5%" and percent(0.18) == "18%" and percent(0.185) == "18,5%"
