"""Заявки: то, что вводит клиент."""
import numpy as np
import pandas as pd

from alfa_ml.synth.population import Population, choose


def generate_applications(ids: np.ndarray, app_dates: pd.DatetimeIndex, pop: Population, cfg: dict,
                          scoring_cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    a = cfg["applications"]
    n = len(ids)
    revenue = pop.truth["true_revenue"].to_numpy()
    step = scoring_cfg["amount_step"]

    ratio = np.exp(rng.normal(np.log(a["loan_to_revenue_median"]), a["loan_to_revenue_sigma"], n))
    amount = np.clip(np.round(ratio * revenue / step) * step, scoring_cfg["min_amount"], a["max_amount"])
    term = choose(rng, a["term_probs"], n).astype(int)
    purpose = choose(rng, a["purpose_probs"], n).astype(object)
    purpose_text = np.where(purpose == "other", rng.choice(a["other_purposes"], size=n), "")

    # Рефинансирование: клиент отмечает 1–2 бизнес-кредита из списка БКИ.
    business = {app: loans for app, loans in pop.bki_loans[pop.bki_loans["is_business"]].groupby("application_id")}
    refinance = [[] for _ in range(n)]
    for i in np.flatnonzero(purpose == "refinancing"):
        loans = business.get(ids[i])
        if loans is None:
            purpose[i] = "working_capital"
            continue
        chosen = loans.iloc[rng.choice(len(loans), size=rng.integers(1, min(2, len(loans)) + 1), replace=False)]
        refinance[i] = chosen["loan_id"].tolist()
        target = chosen["balance"].sum() * rng.uniform(*a["refinance_markup"])
        amount[i] = min(np.ceil(target / step) * step, a["max_amount"])

    return pd.DataFrame({
        "application_id": ids,
        "inn": pop.companies["inn"].to_numpy(),
        "legal_form": pop.companies["legal_form"].to_numpy(),
        "application_date": app_dates,
        "requested_amount": amount,
        "term_months": term,
        "purpose": purpose.astype(str),
        "purpose_text": purpose_text,
        "refinance_loan_ids": refinance,
        "declared_revenue": np.round(revenue * rng.uniform(*cfg["population"]["declared_inflation"], n), -4),
        "bki_consent": True,
    })
