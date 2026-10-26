"""WoE-биннинг, логистическая регрессия и скоркарты на случаях, где ответ известен заранее."""
import numpy as np
import pandas as pd
import pytest

from alfa_ml.features.build import CATEGORICAL, MODEL1_FEATURES, MODEL2_FEATURES
from alfa_ml.metrics import ks, psi
from alfa_ml.models.scorecard import MODEL1_FILE, MODEL2_FILE, Scorecard, load_model
from alfa_ml.models.train import fit_logistic
from alfa_ml.models.woe import fit_categorical, fit_numeric


def _risky_by_value(n=20_000, seed=1):
    """Риск растёт с x; 3% пропусков с высоким риском."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 10, n)
    y = rng.random(n) < 0.02 + 0.01 * x
    x[rng.random(n) < 0.03] = np.nan
    y[np.isnan(x)] = rng.random(np.isnan(x).sum()) < 0.3
    return x, y.astype(int)


def test_numeric_bins_are_monotonic_and_large_enough():
    x, y = _risky_by_value()
    b = fit_numeric("x", x, y, direction=1, min_share=0.05, max_bins=8, missing_min_share=0.05)
    rates = np.array(b.events) / np.array(b.counts)
    assert 2 <= len(b.woe) <= 8 and np.all(np.diff(rates) >= 0) and np.all(np.diff(b.woe) >= 0)
    assert min(b.counts) >= 0.05 * len(y)
    # Пропусков 3% — меньше missing_min_share: они слиты с самым рискованным интервалом.
    assert b.missing_woe == max(b.woe)
    assert b.transform([np.nan, -100.0, 100.0]).tolist() == [max(b.woe), b.woe[0], b.woe[-1]]
    # По умолчанию пропуск от 1% выборки — свой интервал: у этих 30% дефолтов WoE выше всех.
    own = fit_numeric("x", x, y, direction=1)
    assert own.missing_woe > max(own.woe) and own.missing_count == np.isnan(x).sum()


def test_numeric_direction_not_confirmed_gives_one_bin():
    x, y = _risky_by_value()
    b = fit_numeric("x", x, y, direction=-1, missing_min_share=0.05)
    assert len(b.woe) == 1 and b.iv < 0.01


def test_neutral_missing():
    x, y = _risky_by_value()
    b = fit_numeric("x", x, y, direction=1, neutral_missing=True)
    assert b.missing_woe == 0.0 and b.transform([np.nan])[0] == 0.0
    # WoE интервалов считается по заявкам со значением: доли — от их дефолтов и недефолтов.
    present = ~np.isnan(x)
    events, goods = np.array(b.events), np.array(b.counts) - np.array(b.events)
    expected = np.log((events + 0.5) / y[present].sum()) - np.log((goods + 0.5) / (1 - y[present]).sum())
    assert np.allclose(b.woe, expected, atol=1e-6)


def test_categorical_rare_categories_merged_and_unknown_is_risky():
    rng = np.random.default_rng(2)
    values = rng.choice(["a", "b", "c", "rare"], size=10_000, p=[0.5, 0.3, 0.18, 0.02])
    rate = pd.Series(values).map({"a": 0.02, "b": 0.05, "c": 0.10, "rare": 0.09}).to_numpy()
    y = (rng.random(10_000) < rate).astype(int)
    b = fit_categorical("v", values, y, min_share=0.05)
    assert ["c", "rare"] in b.groups and len(b.groups) == 3
    assert b.transform(["unknown"])[0] == max(b.woe)
    # 0/1 и True/False — одни и те же категории.
    flags = fit_categorical("f", [True, False] * 500, [1, 0] * 500)
    assert flags.transform([1, True, "1"]).tolist() == [flags.transform([True])[0]] * 3


def test_logistic_matches_closed_form():
    """Одна бинарная фича: коэффициент — логарифм отношения шансов, свободный член — логарифм шансов при 0."""
    x = np.array([0] * 1000 + [1] * 1000, dtype=float)
    y = np.array([1] * 50 + [0] * 950 + [1] * 200 + [0] * 800, dtype=float)
    intercept, coef, se = fit_logistic(x[:, None], y)
    assert intercept == pytest.approx(np.log(50 / 950))
    assert coef[0] == pytest.approx(np.log(200 / 800) - np.log(50 / 950))
    assert se[0] == pytest.approx(np.sqrt(1 / 50 + 1 / 950 + 1 / 200 + 1 / 800))


def test_scorecard_round_trip(tmp_path):
    x, y = _risky_by_value()
    b = fit_numeric("x", x, y, direction=1)
    card = Scorecard("test", -2.0, {"x": 0.9}, {"x": b})
    card.save(tmp_path / "card.json")
    again = Scorecard.load(tmp_path / "card.json")
    frame = pd.DataFrame({"x": x[:100]})
    assert np.allclose(card.predict_pd(frame), again.predict_pd(frame))


@pytest.mark.parametrize(("file_name", "features"), [(MODEL1_FILE, MODEL1_FEATURES), (MODEL2_FILE, MODEL2_FEATURES)])
def test_trained_models_are_consistent(file_name, features):
    model = load_model(file_name)
    assert set(model.coefficients) <= set(features)
    assert {"purpose", "has_collateral", "max_dpd_24m"} <= set(model.coefficients)
    assert all(c > 0 for c in model.coefficients.values())  # WoE больше — риск больше
    for name, b in model.binnings.items():
        assert b.kind == ("categorical" if name in CATEGORICAL or name.startswith("has_") else "numeric")


def test_ks_and_psi():
    assert ks([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    rng = np.random.default_rng(3)
    base = rng.normal(size=10_000)
    assert psi(base, base) == pytest.approx(0.0)
    assert psi(base, rng.normal(size=10_000)) < 0.01 < 0.25 < psi(base, rng.normal(1.0, 1, 10_000))
