"""Заявки: то, что вводит клиент."""
import numpy as np
import pandas as pd

from alfa_ml.synth.population import Population, choose


def generate_applications(ids: np.ndarray, app_dates: pd.DatetimeIndex, pop: Population, cfg: dict,
                          scoring_cfg: dict, rng: np.random.Generator,
                          detail_rng: np.random.Generator) -> pd.DataFrame:
    """detail_rng — отдельный поток для цели, срока и залога: от него не зависят компании и обороты."""
    a = cfg["applications"]
    n = len(ids)
    revenue = pop.truth["true_revenue"].to_numpy()
    step = scoring_cfg["amount_step"]

    ratio = np.exp(rng.normal(np.log(a["loan_to_revenue_median"]), a["loan_to_revenue_sigma"], n))
    base_amount = ratio * revenue
    term = choose(rng, a["term_probs"], n).astype(int)
    purpose = choose(rng, a["purpose_probs"], n).astype(object)
    rng.integers(0, 3, size=n)  # прежний розыгрыш текста цели «другое»: без него сдвинется поток

    # Рефинансирование: клиент отмечает 1–2 бизнес-кредита из списка БКИ.
    business = {app: loans for app, loans in pop.bki_loans[pop.bki_loans["is_business"]].groupby("application_id")}
    refinance = [[] for _ in range(n)]
    refinance_amount = np.full(n, np.nan)
    for i in np.flatnonzero(purpose == "refinancing"):
        loans = business.get(ids[i])
        if loans is None:
            purpose[i] = "working_capital"
            continue
        chosen = loans.iloc[rng.choice(len(loans), size=rng.integers(1, min(2, len(loans)) + 1), replace=False)]
        refinance[i] = chosen["loan_id"].tolist()
        target = chosen["balance"].sum() * rng.uniform(*a["refinance_markup"])
        refinance_amount[i] = min(np.ceil(target / step) * step, a["max_amount"])
    declared = np.round(revenue * rng.uniform(*cfg["population"]["declared_inflation"], n), -4)

    # Цель по ключам бэкенда; сумма и срок зависят от цели, залог — чаще при покупке активов.
    for group, split in a["purpose_split"].items():
        idx = np.flatnonzero(purpose == group)
        purpose[idx] = choose(detail_rng, split, idx.size)
    factor = pd.Series(purpose).map(a["purpose_amount_factor"]).fillna(1.0).to_numpy()
    amount = np.clip(np.round(base_amount * factor / step) * step, scoring_cfg["min_amount"], a["max_amount"])
    amount = np.where(np.isnan(refinance_amount), amount, refinance_amount)
    for key, probs in a["purpose_term_probs"].items():
        idx = np.flatnonzero(purpose == key)
        term[idx] = choose(detail_rng, probs, idx.size).astype(int)
    has_collateral = detail_rng.random(n) < pd.Series(purpose).map(a["collateral_prob"]).to_numpy()

    return pd.DataFrame({
        "application_id": ids,
        "inn": pop.companies["inn"].to_numpy(),
        "legal_form": pop.companies["legal_form"].to_numpy(),
        "application_date": app_dates,
        "requested_amount": amount,
        "term_months": term,
        "purpose": purpose.astype(str),
        "has_collateral": has_collateral,
        "refinance_loan_ids": refinance,
        "declared_revenue": declared,
        "bki_consent": True,
    })
