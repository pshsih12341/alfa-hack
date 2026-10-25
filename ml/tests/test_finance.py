import numpy as np
import pytest

from alfa_ml.config import load_config
from alfa_ml.finance import annuity_payment, rate_for_pd


@pytest.mark.parametrize(("term", "expected"), [(12, 92_634.51), (24, 50_895.80), (36, 37_163.58)])
def test_annuity_matches_spec_reference(term, expected):
    # Ориентир из спецификации: 1 млн под 20% — 92.6 / 50.9 / 37.2 тыс. в месяц.
    assert annuity_payment(1_000_000, 0.20, term) == pytest.approx(expected, abs=0.01)


def test_annuity_is_vectorized():
    payments = annuity_payment([1_000_000, 2_000_000], [0.18, 0.24], [12, 36])
    assert payments.shape == (2,)
    assert payments[1] > payments[0] * 0.8


@pytest.mark.parametrize(("pd_value", "rate"), [
    (0.0, 0.18), (0.0299, 0.18), (0.03, 0.20), (0.069, 0.20), (0.07, 0.22),
    (0.11, 0.24), (0.15, 0.24), (0.5, 0.24),
])
def test_rate_bucket_boundaries(pd_value, rate):
    buckets = load_config("scoring")["rate_buckets"]
    assert rate_for_pd(pd_value, buckets) == pytest.approx(rate)


def test_rate_for_pd_vectorized():
    buckets = load_config("scoring")["rate_buckets"]
    assert np.allclose(rate_for_pd(np.array([0.01, 0.05, 0.09, 0.13]), buckets), [0.18, 0.20, 0.22, 0.24])
