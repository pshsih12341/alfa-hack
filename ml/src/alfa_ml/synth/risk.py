"""Истинная формула риска. По ней генерируются дефолты; модели её не видят."""
import numpy as np
import pandas as pd

from alfa_ml.features import external, statements
from alfa_ml.finance import annuity_payment, rate_for_pd
from alfa_ml.synth.flows import month_ordinal

REFERENCE_RATE = 0.20  # ставка для первой оценки PD, до выбора корзины


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def risk_drivers(batch, gen_cfg: dict, scoring_cfg: dict) -> pd.DataFrame:
    """Вклады в логит PD, кроме зависящих от платежа по новому кредиту, плюс данные для DSCR.

    batch — объект с таблицами выборки: companies, persons, bki_subjects, bki_loans,
    applications, monthly, truth.
    """
    apps = batch.applications.set_index("application_id")
    ids = apps.index
    truth = batch.truth.set_index("application_id").reindex(ids)
    companies = batch.companies.set_index("application_id").reindex(ids)
    feat = scoring_cfg["features"]
    c = gen_cfg["risk"]["coefficients"]
    threshold = feat["owner_share_threshold"]

    loans = external.kept_loans(batch.bki_loans, batch.applications)
    dpd = external.dpd_category(external.max_dpd(batch.bki_subjects, batch.persons, ids, threshold))
    inquiries = external.borrower_inquiries(batch.bki_subjects, ids)
    track = external.worst_track_record(batch.persons, ids, threshold)

    # Поток для DSCR: по выпискам, если месяцев достаточно, иначе по выручке и марже.
    summary = statements.flow_summary(batch.monthly, feat["conservative_flow_percentile"]).reindex(ids)
    revenue = truth["true_revenue"]
    estimated = revenue / 12 * truth["margin"] * scoring_cfg["stage1"]["flow_haircut"]
    enough = summary["months"].fillna(0) >= scoring_cfg["stage2"]["min_statement_months"]
    ip = (companies["legal_form"] == "ip").astype(float)
    flow = summary["conservative_flow"].where(enough, estimated) - ip * feat["ip_living_cost_monthly"]

    leverage = (apps["requested_amount"] + external.business_debt(loans, ids)) / revenue
    tax_debt = (companies["ens_debt"] > feat["tax_debt_threshold"]).astype(float)
    inter = gen_cfg["risk"]["interactions"]
    base = (c["ip"] * ip
            + c["log_age"] * np.log1p(truth["age_months"] / 6)
            + truth["okved_group"].map(c["okved"])
            + c["log_revenue"] * np.log(revenue / 1e7)
            + c["leverage"] * np.log1p(3 * leverage)
            + c["volatility"] * truth["volatility"]
            + c["growth"] * truth["growth"]
            + dpd.map(c["dpd"])
            + c["inquiries"] * np.minimum(inquiries, 10)
            + c["tax_debt"] * tax_debt
            + track.map(c["track_record"])
            + c["top_customer"] * truth["top_customer_share"]
            + apps["purpose"].map(c["purpose"])
            + c["collateral"] * apps["has_collateral"]
            + inter["young_leverage"] * (truth["age_months"] < 12) * np.log1p(3 * leverage)
            + inter["tax_debt_severe_dpd"] * tax_debt * dpd.isin(["30-89", "90+"])
            + gen_cfg["risk"]["latent_noise_sd"] * truth["latent"])
    return pd.DataFrame({
        "base": base,
        "volatility": truth["volatility"],
        "flow": flow,
        "existing_payments": external.existing_payments(loans, ids),
        "amount": apps["requested_amount"],
        "term": apps["term_months"],
        "has_collateral": apps["has_collateral"],
    })


def true_pd(drivers: pd.DataFrame, intercept: float, gen_cfg: dict, scoring_cfg: dict):
    """PD и ставка кредита. Ставка зависит от PD и залога, а PD — от платежа по этой ставке: один шаг уточнения."""
    c = gen_cfg["risk"]["coefficients"]
    vol_low_dscr = gen_cfg["risk"]["interactions"]["volatility_low_dscr"]
    base = drivers["base"].to_numpy()
    volatility = drivers["volatility"].to_numpy()
    flow = drivers["flow"].to_numpy()
    existing = drivers["existing_payments"].to_numpy()
    amount = drivers["amount"].to_numpy()
    term = drivers["term"].to_numpy()
    collateral = drivers["has_collateral"].to_numpy(dtype=bool)

    def logit(rate):
        dscr = flow / (annuity_payment(amount, rate, term) + existing)
        below_1 = dscr < 1
        return (intercept + base + c["log_dscr"] * np.log(np.clip(dscr, 0.2, 5.0)) + c["dscr_below_1"] * below_1
                + vol_low_dscr * volatility * below_1)

    first = sigmoid(logit(REFERENCE_RATE))
    rate = np.where(collateral, rate_for_pd(first, scoring_cfg["collateral_rate_buckets"]),
                    rate_for_pd(first, scoring_cfg["rate_buckets"]))
    return sigmoid(logit(rate)), rate


def cycle_shift(dates, gen_cfg: dict) -> np.ndarray:
    """Сдвиг логита от экономического цикла по месяцу заявки (синусоида)."""
    cycle = gen_cfg["risk"]["cycle"]
    months = month_ordinal(dates) - month_ordinal([pd.Timestamp(cycle["start_month"])])[0]
    return cycle["amplitude"] * np.sin(2 * np.pi * months / cycle["period_months"])


def calibrate_intercept(drivers: pd.DataFrame, target_rate: float, gen_cfg: dict, scoring_cfg: dict) -> float:
    """Свободный член, при котором средний PD равен целевой доле дефолтов (бисекция)."""
    lo, hi = -20.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        mean_pd = true_pd(drivers, mid, gen_cfg, scoring_cfg)[0].mean()
        lo, hi = (mid, hi) if mean_pd < target_rate else (lo, mid)
    return (lo + hi) / 2
