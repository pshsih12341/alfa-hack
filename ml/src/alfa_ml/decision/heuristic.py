"""Временная формула PD этапа 1 — до обучения модели 1.

Логистическая формула на тех же 11 фичах модели 1. Веса заданы вручную по направлениям риска
из спецификации, свободный член подобран на train так, чтобы средний PD был около 6%.
Интерфейс такой же, как будет у обученной модели: predict_pd(матрица фич) → массив PD.
"""
import numpy as np
import pandas as pd

from alfa_ml.features.external import dpd_category

MODEL_VERSION = "stage1-heuristic-2026.10.25"
# Подобран на train (19 000 заявок без стоп-правил): средний PD 6.0%.
# Gini: train 0.590, test_oot 0.612. Доли зон: < 5% — 70%, 5–30% — 28%, > 30% — 2.4%.
INTERCEPT = -3.7897

OKVED = {"trade": 0.0, "food_service": 0.4, "construction": 0.3, "transport": 0.1, "manufacturing": -0.1,
         "it_services": -0.2, "agriculture": 0.2, "other": 0.0}
DPD = {"0": 0.0, "1-29": 0.4, "30-89": 1.0, "90+": 1.8, "no_history": 0.3}
TRACK = {"ok": 0.0, "first": 0.2, "problem": 0.7}
SOURCE = {"alfa_full": 0.0, "fns": 0.0, "alfa_partial": 0.2, "declared": 0.3}


def logit(x: pd.DataFrame) -> np.ndarray:
    # Выручка неизвестна (ноль или ошибка в данных) — считаем как рискованный случай:
    # нагрузка 100% выручки и минимальный размер бизнеса.
    leverage = (x["loan_to_revenue"] + x["debt_to_revenue"]).clip(lower=0).fillna(1.0)
    value = (INTERCEPT
             + 0.15 * (x["legal_form"] == "ip")
             - 0.45 * np.log1p(x["business_age_months"].clip(lower=0) / 6)
             + x["okved_group"].map(OKVED).fillna(0.0)
             + 1.2 * np.log1p(3 * leverage)
             - 0.15 * np.log(x["revenue_size"].fillna(1e5).clip(lower=1e5) / 1e7)
             + dpd_category(x["max_dpd_24m"]).map(DPD)
             + 0.15 * x["bki_inquiries_90d"].clip(upper=10)
             + 0.6 * x["has_tax_debt"]
             + x["owner_track_record"].map(TRACK).fillna(0.0)
             + x["revenue_source"].map(SOURCE).fillna(0.0))
    return value.to_numpy(dtype=float)


def predict_pd(x: pd.DataFrame) -> np.ndarray:
    """PD этапа 1 по 11 фичам модели 1 (build.model1_features)."""
    return 1 / (1 + np.exp(-logit(x)))
