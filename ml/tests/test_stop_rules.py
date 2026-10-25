import datetime as dt

import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.decision.stop_rules import check_stop_rules, client_message, full_months

RULES = load_config("rules")
WINDOWS = load_config("scoring")["stop_rules"]
AS_OF = dt.date(2026, 11, 1)


def _org(legal_form="ooo", status="active", bankruptcy=False, rfm=False):
    return pd.DataFrame([{"inn": "7707083893", "legal_form": legal_form, "status": status,
                          "bankruptcy_procedure": bankruptcy, "in_rfm_list": rfm}])


def _persons(ended=None, rfm=(False, False)):
    return pd.DataFrame({
        "inn": ["500100732259", "111"], "is_director": [True, False], "share": [0.0, 1.0],
        "bankruptcy_end_date": [pd.Timestamp(ended) if ended else pd.NaT, pd.NaT], "in_rfm_list": list(rfm),
    })


@pytest.mark.parametrize(("start", "end", "months"), [
    ("2023-01-15", "2026-01-14", 35), ("2023-01-15", "2026-01-15", 36), ("2023-01-31", "2023-02-28", 0),
])
def test_full_months(start, end, months):
    assert full_months(dt.date.fromisoformat(start), dt.date.fromisoformat(end)) == months


@pytest.mark.parametrize(("legal_form", "ended", "blocked"), [
    ("ooo", "2023-11-02", True),    # 35 полных месяцев — директору ещё нельзя
    ("ooo", "2023-11-01", False),   # ровно 36 — можно
    ("ip", "2021-11-02", True),     # 59 — ИП ещё нельзя
    ("ip", "2021-11-01", False),    # ровно 60 — можно
])
def test_owner_bankruptcy_boundaries(legal_form, ended, blocked):
    hits = check_stop_rules(_org(legal_form), _persons(ended), AS_OF, RULES, WINDOWS)
    assert ("owner_bankruptcy" in [h.id for h in hits]) is blocked


def test_participant_bankruptcy_is_not_a_stop_rule():
    persons = _persons()
    persons.loc[1, "bankruptcy_end_date"] = pd.Timestamp("2026-01-01")  # участник, не директор
    assert check_stop_rules(_org(), persons, AS_OF, RULES, WINDOWS) == []


def test_registry_rules():
    ids = [h.id for h in check_stop_rules(_org(status="liquidating", bankruptcy=True), _persons(), AS_OF, RULES, WINDOWS)]
    assert ids == ["inactive_status", "company_bankruptcy"]
    assert check_stop_rules(_org(), _persons(), AS_OF, RULES, WINDOWS) == []


def test_rfm_list_message_is_neutral():
    hits = check_stop_rules(_org(status="excluded"), _persons(rfm=(False, True)), AS_OF, RULES, WINDOWS)
    assert [h.id for h in hits] == ["inactive_status", "rfm_list"]
    message = client_message(hits)
    assert message == "К сожалению, сейчас мы не можем предоставить кредит."
    assert "111" in hits[1].internal_reason  # причина — только во внутреннем логе
