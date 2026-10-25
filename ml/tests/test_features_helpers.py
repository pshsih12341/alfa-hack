import numpy as np
import pandas as pd
import pytest

from alfa_ml.features import external, statements


def test_dpd_category_keeps_no_history_apart_from_zero():
    days = pd.Series([0, 1, 29, 30, 89, 90, 400, np.nan])
    assert external.dpd_category(days).tolist() == ["0", "1-29", "1-29", "30-89", "30-89", "90+", "90+", "no_history"]


def test_owner_mask_uses_strict_share_threshold():
    persons = pd.DataFrame({"is_director": [True, False, False], "share": [0.0, 0.25, 0.26]})
    assert external.owner_mask(persons, 0.25).tolist() == [True, False, True]


def test_max_dpd_takes_worst_of_borrower_and_owners():
    persons = pd.DataFrame({
        "application_id": [1, 1, 1], "inn": ["d", "p_big", "p_small"],
        "is_director": [True, False, False], "share": [0.0, 0.6, 0.1],
    })
    subjects = pd.DataFrame({
        "application_id": [1, 1, 1, 1],
        "subject_inn": ["company", "d", "p_big", "p_small"],
        "is_borrower": [True, False, False, False],
        "has_history": [True, True, True, True],
        "max_dpd_24m": [0.0, 10.0, 45.0, 200.0],
    })
    # Участник с долей 10% не собственник: его 200 дней не учитываются.
    assert external.max_dpd(subjects, persons, [1, 2], 0.25).tolist()[0] == 45.0
    assert np.isnan(external.max_dpd(subjects, persons, [1, 2], 0.25).tolist()[1])


def test_kept_loans_drop_refinanced():
    loans = pd.DataFrame({"application_id": [1, 1, 2], "loan_id": [10, 11, 12], "is_business": [True, True, True],
                          "balance": [100.0, 200.0, 300.0], "monthly_payment": [10.0, 20.0, 30.0]})
    apps = pd.DataFrame({"application_id": [1, 2], "refinance_loan_ids": [[11], []]})
    kept = external.kept_loans(loans, apps)
    assert sorted(kept["loan_id"]) == [10, 12]
    assert external.business_debt(kept, [1, 2]).tolist() == [100.0, 300.0]
    assert external.existing_payments(kept, [1, 2, 3]).tolist() == [10.0, 30.0, 0.0]


def test_worst_track_record_order():
    persons = pd.DataFrame({"application_id": [1, 1, 2], "is_director": [True, False, True], "share": [0.0, 0.5, 1.0],
                            "track_record": ["ok", "first", "problem"]})
    assert external.worst_track_record(persons, [1, 2], 0.25).tolist() == ["first", "problem"]


def _month(app_id, month, **values):
    row = {col: 0.0 for col in [*statements.OPERATIONAL_INFLOWS, *statements.OPERATIONAL_OUTFLOWS,
                                "inflow_own_transfer", "inflow_loans", "outflow_loan_payments", "outflow_owner_payouts"]}
    row.update(application_id=app_id, month=pd.Timestamp(month), **values)
    return row


def test_cash_flow_ignores_transfers_loans_and_payouts():
    monthly = pd.DataFrame([_month(1, "2025-01-01", inflow_customers=1000, inflow_own_transfer=500, inflow_loans=900,
                                   outflow_suppliers=600, outflow_loan_payments=300, outflow_owner_payouts=200,
                                   outflow_other_debt=50)])
    flows = statements.monthly_cash_flow(monthly)
    assert flows["free_cash_flow"].iloc[0] == pytest.approx(1000 - 600 - 50)


def test_flow_summary_conservative_percentile():
    monthly = pd.DataFrame([_month(1, f"2025-{m:02d}-01", inflow_customers=100.0 * m) for m in range(1, 6)])
    summary = statements.flow_summary(monthly, 20).loc[1]
    assert summary["months"] == 5
    assert summary["conservative_flow"] == pytest.approx(180.0)  # 20-й перцентиль из 100…500
