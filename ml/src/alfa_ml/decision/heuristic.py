"""Временные формулы PD этапов 1 и 2 — до обучения моделей 1 и 2.

Логистические формулы на тех же фичах, что у моделей (13 и 17). Веса заданы вручную по направлениям
риска из спецификации, свободные члены подобраны на train так, чтобы средний PD был около 6%.
Интерфейс такой же, как будет у обученных моделей: predict_pd(матрица фич) → массив PD.
"""
import numpy as np
import pandas as pd

from alfa_ml.features.external import dpd_category

MODEL_VERSION = "stage1-heuristic-2026.10.26"
# Подобран на train (19 000 заявок без стоп-правил): средний PD 6.0%.
# Gini: train 0.598, test_oot 0.624 (без цели и залога 0.591 и 0.616). Доли зон: < 5% — 70%, 5–30% — 27%, > 30% — 2.4%.
INTERCEPT = -3.7680

OKVED = {"trade": 0.0, "food_service": 0.4, "construction": 0.3, "transport": 0.1, "manufacturing": -0.1,
         "it_services": -0.2, "agriculture": 0.2, "other": 0.0}
DPD = {"0": 0.0, "1-29": 0.4, "30-89": 1.0, "90+": 1.8, "no_history": 0.3}
TRACK = {"ok": 0.0, "first": 0.2, "problem": 0.7}
SOURCE = {"alfa_full": 0.0, "fns": 0.0, "alfa_partial": 0.2, "declared": 0.3}
# Деньги на текущие расходы — признак кассового разрыва; покупка активов — вложение с понятной отдачей.
PURPOSE = {"working_capital": 0.0, "current_expenses": 0.35, "repair": 0.1, "equipment": -0.15, "property": -0.1,
           "real_estate": -0.2, "refinancing": 0.2}
COLLATERAL = -0.25  # с залогом заёмщику есть что терять


def _common(x: pd.DataFrame) -> pd.Series:
    """Вклады фич, общих для моделей 1 и 2: форма, возраст, отрасль, нагрузка, размер, БКИ, налоги, опыт,
    цель кредита и залог."""
    # Выручка неизвестна (ноль или ошибка в данных) — считаем как рискованный случай:
    # нагрузка 100% выручки и минимальный размер бизнеса.
    leverage = (x["loan_to_revenue"] + x["debt_to_revenue"]).clip(lower=0).fillna(1.0)
    return (0.15 * (x["legal_form"] == "ip")
            - 0.45 * np.log1p(x["business_age_months"].clip(lower=0) / 6)
            + x["okved_group"].map(OKVED).fillna(0.0)
            + 1.2 * np.log1p(3 * leverage)
            - 0.15 * np.log(x["revenue_size"].fillna(1e5).clip(lower=1e5) / 1e7)
            + dpd_category(x["max_dpd_24m"]).map(DPD)
            + 0.15 * x["bki_inquiries_90d"].clip(upper=10)
            + 0.6 * x["has_tax_debt"]
            + x["owner_track_record"].map(TRACK).fillna(0.0)
            + x["purpose"].map(PURPOSE).fillna(0.0)
            + COLLATERAL * x["has_collateral"])


def logit(x: pd.DataFrame) -> np.ndarray:
    value = INTERCEPT + _common(x) + x["revenue_source"].map(SOURCE).fillna(0.0)
    return value.to_numpy(dtype=float)


def predict_pd(x: pd.DataFrame) -> np.ndarray:
    """PD этапа 1 по 13 фичам модели 1 (build.model1_features)."""
    return 1 / (1 + np.exp(-logit(x)))


MODEL2_VERSION = "stage2-heuristic-2026.10.26"
# Подобран на train (заявки без стоп-правил, с выписками от 3 месяцев): средний PD 6.0%.
# Gini: train 0.676, test_oot 0.697 (без цели и залога 0.671 и 0.691); PD ≤ 15% у 89% заявок.
INTERCEPT2 = -5.5259


def logit2(x: pd.DataFrame) -> np.ndarray:
    dscr = x["dscr"].fillna(0.2)
    value = (INTERCEPT2 + _common(x)
             - 0.8 * np.log(dscr.clip(0.2, 5.0)) + 0.6 * (dscr < 1)
             + 3.0 * x["fcf_volatility"].clip(upper=1.0).fillna(0.3)
             # Падение оборотов опаснее роста; нет года выписок — нейтрально.
             - 1.0 * (x["turnover_trend"] - 1).clip(-0.5, 0.5).fillna(0.0)
             # Выписки показали меньше заявленного — признак завышения выручки в анкете.
             + 0.8 * (0.9 - x["revenue_consistency"]).clip(lower=0.0).fillna(0.0)
             + 1.0 * x["top_customer_share"].fillna(0.3))
    return value.to_numpy(dtype=float)


def predict_pd2(x: pd.DataFrame) -> np.ndarray:
    """PD этапа 2 по 17 фичам модели 2 (build.model2_features)."""
    return 1 / (1 + np.exp(-logit2(x)))
