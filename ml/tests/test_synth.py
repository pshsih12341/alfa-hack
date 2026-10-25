import numpy as np
import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.inn import is_valid_inn
from alfa_ml.synth.datasets import Context, Segment, build_sample
from alfa_ml.synth.ids import IdCounter, InnFactory

MONTHS = ("2024-01", "2024-06")


def _build(seed: int = 7, size: int = 2000):
    gen, scoring = load_config("generator"), load_config("scoring")
    ctx = Context(gen, scoring, InnFactory(np.random.default_rng(seed)), IdCounter(), IdCounter())
    batch, intercept = build_sample([Segment(size, gen)], MONTHS, ctx, np.random.SeedSequence(seed))
    return batch, intercept, gen


@pytest.fixture(scope="module")
def sample():
    return _build()


def test_same_seed_gives_same_data(sample):
    batch, intercept, _ = sample
    again, intercept_again, _ = _build()
    assert intercept == intercept_again
    pd.testing.assert_frame_equal(batch.applications, again.applications)
    pd.testing.assert_frame_equal(batch.monthly, again.monthly)
    pd.testing.assert_frame_equal(batch.labels, again.labels)


def test_shares_of_outliers_and_stop_rules(sample):
    batch, _, gen = sample
    labels = batch.labels
    assert (labels["outlier_type"] != "").mean() == pytest.approx(gen["anomalies"]["outlier_share"], abs=0.005)
    assert (labels["heuristic_reason"] != "").mean() == pytest.approx(gen["anomalies"]["stop_rule_share"], abs=0.005)
    # Выброс и стоп-правило у одной заявки не совпадают.
    assert not ((labels["outlier_type"] != "") & (labels["heuristic_reason"] != "")).any()


def test_default_rate_calibrated(sample):
    batch, _, gen = sample
    passed = batch.labels["heuristic_reason"] == ""
    assert batch.labels.loc[passed, "true_pd"].mean() == pytest.approx(gen["target_default_rate"], abs=0.002)


def test_statement_months_are_full_months_before_application(sample):
    batch, _, _ = sample
    monthly = batch.monthly.merge(batch.applications[["application_id", "application_date"]], on="application_id")
    monthly = monthly.merge(batch.companies[["application_id", "registration_date"]], on="application_id")
    app_month = monthly["application_date"].dt.to_period("M")
    month = monthly["month"].dt.to_period("M")
    assert (month < app_month).all()
    assert (month > monthly["registration_date"].dt.to_period("M")).all()
    assert batch.monthly.groupby("application_id").size().max() <= 12


def test_registry_data_consistent(sample):
    batch, _, _ = sample
    companies, persons = batch.companies, batch.persons
    assert companies["inn"].map(is_valid_inn).all() and persons["inn"].map(is_valid_inn).all()
    ip = companies["legal_form"] == "ip"
    assert (companies.loc[ip, "inn"].str.len() == 12).all() and (companies.loc[~ip, "inn"].str.len() == 10).all()
    assert (persons.groupby("application_id")["is_director"].sum() == 1).all()
    shares = persons.groupby("application_id")["share"].sum()
    assert np.allclose(shares.reindex(companies["application_id"]).to_numpy(), 1.0)


def test_stop_rules_leave_traces_in_registries(sample):
    batch, _, _ = sample
    reasons = batch.labels.set_index("application_id")["heuristic_reason"]
    companies = batch.companies.set_index("application_id")
    inactive = reasons[reasons == "inactive_status"].index
    assert (companies.loc[inactive, "status"] != "active").all()
    assert companies.loc[reasons[reasons == "company_bankruptcy"].index, "bankruptcy_procedure"].all()
    clean = reasons[reasons == ""].index
    assert (companies.loc[clean, "status"] == "active").all()
    assert not companies.loc[clean, "bankruptcy_procedure"].any()


def test_refinanced_loans_belong_to_borrower(sample):
    batch, _, _ = sample
    refinanced = batch.applications[["application_id", "refinance_loan_ids"]].explode("refinance_loan_ids").dropna()
    loans = batch.bki_loans.set_index("loan_id")
    owners = loans.loc[refinanced["refinance_loan_ids"].astype("int64"), "application_id"].to_numpy()
    assert (owners == refinanced["application_id"].to_numpy()).all()
    assert loans.loc[refinanced["refinance_loan_ids"].astype("int64"), "is_business"].all()
