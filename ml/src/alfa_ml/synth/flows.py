"""Помесячные обороты по счёту за 12 месяцев до заявки, суммы по категориям операций."""
import numpy as np
import pandas as pd

from alfa_ml.synth.population import Population


def month_ordinal(dates) -> np.ndarray:
    """Номер месяца: год × 12 + (месяц − 1)."""
    dates = pd.DatetimeIndex(dates)
    return (dates.year * 12 + dates.month - 1).to_numpy()


def available_months(app_dates, registration_dates, window: int) -> np.ndarray:
    """Полных месяцев оборотов до заявки: месяц регистрации неполный и не считается."""
    return np.clip(month_ordinal(app_dates) - month_ordinal(registration_dates) - 1, 0, window)


def generate_monthly_flows(pop: Population, app_dates: pd.DatetimeIndex, cfg: dict, rng: np.random.Generator,
                           one_off: np.ndarray, shocked: np.ndarray, shock: dict) -> pd.DataFrame:
    """Строка на месяц: поступления и списания по категориям, поступления от крупнейшего покупателя.

    one_off — строки с разовым крупным контрактом; shocked — строки, где в последние
    shock["months"] месяцев поступления меняются на shock["revenue"].
    """
    fl = cfg["flows"]
    comp, truth = pop.companies, pop.truth
    n, window = len(comp), fl["months"]
    rel = np.arange(-window, 0)
    month_ord = month_ordinal(app_dates)[:, None] + rel
    life = month_ord - month_ordinal(comp["registration_date"])[:, None]
    available = life >= 1

    groups = truth["okved_group"].to_numpy()
    season = _seasonality(fl["seasonality"], groups, month_ord % 12)
    growth = truth["growth"].to_numpy()
    trend = (1 + growth)[:, None] ** ((rel + window) / 12)
    ramp = 1 - np.exp(-np.maximum(life, 0) / fl["ramp_months"])
    sigma = truth["volatility"].to_numpy()[:, None]
    noise = np.exp(rng.normal(-sigma ** 2 / 2, sigma, (n, window)))
    dip = np.where(rng.random((n, window)) < fl["dip_prob"], rng.uniform(*fl["dip_depth"], (n, window)), 1.0)
    shock_factor = np.where(shocked[:, None] & (rel >= -shock.get("months", 0)), 1 + shock.get("revenue", 0.0), 1.0)
    base = truth["true_revenue"].to_numpy() / 12
    inflow = base[:, None] * season * trend * ramp * noise * dip * shock_factor

    # Разовый крупный контракт — реальный выброс в одном из доступных месяцев.
    extra = np.zeros((n, window))
    rows = np.flatnonzero(one_off & available.any(axis=1))
    if rows.size:
        cols = np.array([rng.choice(np.flatnonzero(available[r])) for r in rows])
        extra[rows, cols] = base[rows] * rng.uniform(*cfg["anomalies"]["one_off_multiplier"], rows.size)
    total_in = inflow + extra

    # Расходы: постоянная часть не падает вместе с выручкой, переменная — следует за ней.
    margin = truth["margin"].to_numpy()
    fixed_share = fl["fixed_cost_share"]
    fixed = ((base * (1 - margin) * fixed_share)[:, None] * np.maximum(ramp, 0.5)
             * (1 + rng.normal(0, 0.05, (n, window))))
    operating_out = fixed + total_in * ((1 - margin) * (1 - fixed_share))[:, None]
    other_debt = np.where(rng.random((n, window)) < fl["other_debt_prob"],
                          base[:, None] * rng.uniform(0.05, 0.2, (n, window)), 0.0)

    acquiring = _by_group(fl["acquiring_share"], groups) * np.exp(rng.normal(0, 0.2, n))
    cash = _by_group(fl["cash_share"], groups) * np.exp(rng.normal(0, 0.2, n))
    scale = np.minimum(1.0, 0.95 / (acquiring + cash))
    acquiring, cash = acquiring * scale, cash * scale
    customers = inflow * (1 - acquiring - cash)[:, None]
    top_share = np.clip(truth["top_customer_share"].to_numpy()[:, None] * (1 + rng.normal(0, 0.1, (n, window))), 0, 1)

    split = fl["cost_split"]
    weights = np.array(list(split.values()))[None, :] * np.exp(rng.normal(0, 0.15, (n, len(split))))
    ip = (comp["legal_form"] == "ip").to_numpy()
    no_staff = ip & (rng.random(n) < fl["ip_no_staff_share"])
    weights[no_staff, list(split).index("salary")] = 0.0
    weights /= weights.sum(axis=1, keepdims=True)

    business = pop.bki_loans[pop.bki_loans["is_business"]].groupby("application_id")
    ids = comp["application_id"]
    payments = business["monthly_payment"].sum().reindex(ids).fillna(0.0).to_numpy()
    balances = business["balance"].sum().reindex(ids).fillna(0.0).to_numpy()
    loans_in = np.zeros((n, window))
    rows = np.flatnonzero((balances > 0) & available.any(axis=1) & (rng.random(n) < fl["loan_received_prob"]))
    if rows.size:
        cols = np.array([rng.choice(np.flatnonzero(available[r])) for r in rows])
        loans_in[rows, cols] = 1.2 * balances[rows]

    free_cash_flow = total_in - operating_out - other_debt
    ip_payouts = np.where(ip[:, None], np.maximum(free_cash_flow, 0) * rng.uniform(*fl["ip_payout_share"], (n, window)), 0.0)
    dividends = np.where(~ip[:, None] & (rng.random((n, window)) < fl["dividend_prob"]),
                         np.maximum(free_cash_flow, 0) * rng.uniform(0.5, 2.0, (n, window)), 0.0)
    own_transfer = np.where(rng.random((n, window)) < fl["own_transfer_prob"],
                            total_in * rng.uniform(0.1, 0.5, (n, window)), 0.0)

    columns = {
        "inflow_customers": customers + extra,
        "inflow_acquiring": inflow * acquiring[:, None],
        "inflow_cash": inflow * cash[:, None],
        "inflow_own_transfer": own_transfer,
        "inflow_loans": loans_in,
        "inflow_owner_funding": np.where(rng.random((n, window)) < fl["owner_funding_prob"],
                                         base[:, None] * rng.uniform(0.2, 1.0, (n, window)), 0.0),
        **{f"outflow_{name}": operating_out * weights[:, [i]] for i, name in enumerate(split)},
        "outflow_other_debt": other_debt,
        "outflow_own_transfer": own_transfer,
        "outflow_loan_payments": np.repeat(payments[:, None], window, axis=1),
        "outflow_owner_payouts": ip_payouts + dividends,
        "top_customer_inflow": np.maximum(customers * top_share, extra),
    }
    r, c = np.nonzero(available)
    ordinals = month_ord[r, c]
    return pd.DataFrame({
        "application_id": ids.to_numpy()[r],
        "month": pd.to_datetime(pd.DataFrame({"year": ordinals // 12, "month": ordinals % 12 + 1, "day": 1})),
        **{name: np.round(values[r, c], 2) for name, values in columns.items()},
    })


def _seasonality(table: dict, groups: np.ndarray, calendar_month: np.ndarray) -> np.ndarray:
    profiles = {}
    for name in np.unique(groups):
        profile = np.asarray(table.get(name, table["default"]), dtype=float)
        profiles[name] = profile / profile.mean()
    matrix = np.stack([profiles[name] for name in groups])
    return np.take_along_axis(matrix, calendar_month, axis=1)


def _by_group(mapping: dict, groups: np.ndarray) -> np.ndarray:
    return pd.Series(groups).map(mapping).fillna(mapping["default"]).to_numpy(dtype=float)
