"""Логика этапа 2 на ручных выписках: ООО, поступления 1 млн в месяц, консервативный поток задаётся расходами."""
import numpy as np
import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.decision.stage1 import Application
from alfa_ml.decision.stage2 import decide_stage2
from alfa_ml.finance import annuity_payment
from alfa_ml.sources.schema import TURNOVER_COLUMNS
from test_stage1 import AS_OF, _source

SCORING = load_config("scoring")
RULES = load_config("rules")
FLAT = pd.DataFrame(1.0, index=list(SCORING["okved_groups"]), columns=range(1, 13))


def _statements(months=12, inflow=1_000_000.0, outflow=900_000.0):
    """Каждый месяц одинаковый: свободный поток = inflow − outflow."""
    dates = pd.date_range(end=AS_OF - pd.DateOffset(months=1), periods=months, freq="MS")
    frame = pd.DataFrame({"application_id": 0, "month": dates, **{c: 0.0 for c in TURNOVER_COLUMNS}})
    frame["inflow_customers"], frame["outflow_suppliers"] = inflow, outflow
    frame["top_customer_inflow"] = inflow * 0.3
    return frame


def _decide(credit_sum, term, predict=lambda x: np.full(len(x), 0.02), statements=None, source=None):
    app = Application(credit_sum, term, "working_capital", (), 12_000_000.0)
    return decide_stage2(source or _source(), _statements() if statements is None else statements, app, AS_OF,
                         SCORING, RULES, FLAT, predict_pd=predict)


def test_too_few_months_rejected_with_advice():
    decision = _decide(1_000_000, 12, statements=_statements(months=2))
    assert decision.decision == "REJECTED" and decision.stage == 2
    assert "3 полных месяца" in decision.client_message


def test_approved_on_statements():
    # Поток 100 тыс.: 1 млн на 12 мес под 18% — платёж 91.7 тыс., DSCR 1.09 — не проходит; на 24 мес — 2.0.
    decision = _decide(1_000_000, 24)
    assert decision.decision == "APPROVED" and decision.approved.rate == 0.18
    assert decision.approved.monthly_payment == round(float(annuity_payment(1_000_000, 0.18, 24)))


def test_offer_when_requested_fails_dscr():
    decision = _decide(1_000_000, 12)
    assert decision.decision == "OFFER" and decision.documents_required is None
    first, second = decision.offers
    assert first.term_months == 12 and first.credit_sum < 1_000_000
    assert 100_000 / float(annuity_payment(first.credit_sum, 0.18, 12)) >= 1.25
    assert (second.credit_sum, second.term_months) == (1_000_000, 18)


def test_rejected_when_nothing_passes():
    decision = _decide(1_000_000, 12, predict=lambda x: np.full(len(x), 0.4))
    assert decision.decision == "REJECTED" and decision.pd == pytest.approx(0.4)


def test_rate_climbs_buckets():
    # PD 5% — не влезает в корзину 18% (до 3%), влезает в 20% (до 7%).
    decision = _decide(300_000, 24, predict=lambda x: np.full(len(x), 0.05))
    assert decision.decision == "APPROVED" and decision.approved.rate == 0.20
    # PD 13% — только последняя корзина 24% (до отсечки 15%).
    assert _decide(300_000, 24, predict=lambda x: np.full(len(x), 0.13)).approved.rate == 0.24


def test_rate_depends_on_payment():
    """Чем выше ставка, тем ниже DSCR и выше PD: клетка получает первую корзину, где PD в её интервале."""
    def predict(x):
        return np.where(x["dscr"] >= 3.0, 0.02, 0.05)
    decision = _decide(1_000_000, 36, predict=predict)  # DSCR при 18% чуть ниже 3 → PD 5% → корзина 20%
    assert decision.approved.rate == 0.20


def test_stop_rule_rejects_at_stage_two():
    decision = _decide(300_000, 24, source=_source(status="excluded"))
    assert decision.decision == "REJECTED" and decision.stop_rules == ["inactive_status"] and decision.stage == 2
