"""Финансовые формулы: аннуитетный платёж и ставка по риску."""
import numpy as np


def annuity_payment(amount, rate_annual, term_months):
    """Ежемесячный аннуитетный платёж."""
    amount = np.asarray(amount, dtype=float)
    monthly = np.asarray(rate_annual, dtype=float) / 12
    term = np.asarray(term_months, dtype=float)
    return amount * monthly / (1 - (1 + monthly) ** -term)


def rate_for_pd(pd_values, buckets: list[dict]):
    """Ставка корзины, в интервал которой попадает PD.

    Граница интервала относится к следующей корзине: PD ровно 3% — уже 20%.
    PD выше последней границы получает ставку последней корзины.
    """
    bounds = np.array([bucket["max_pd"] for bucket in buckets[:-1]])
    rates = np.array([bucket["rate"] for bucket in buckets])
    return rates[np.searchsorted(bounds, np.asarray(pd_values, dtype=float), side="right")]
