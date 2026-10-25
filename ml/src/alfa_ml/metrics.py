"""Метрики качества моделей."""
import numpy as np
import pandas as pd


def gini(target, score) -> float:
    """Gini = 2 × AUC − 1; AUC — через ранги (статистика Манна — Уитни)."""
    target = np.asarray(target, dtype=bool)
    ranks = pd.Series(np.asarray(score, dtype=float)).rank().to_numpy()
    positives = target.sum()
    negatives = target.size - positives
    auc = (ranks[target].sum() - positives * (positives + 1) / 2) / (positives * negatives)
    return float(2 * auc - 1)


def ks(target, score) -> float:
    """Колмогоров — Смирнов: наибольшее расхождение долей дефолтов и недефолтов со скором не выше порога."""
    target = np.asarray(target, dtype=bool)
    score = np.asarray(score, dtype=float)
    order = np.argsort(score, kind="stable")
    bad = np.cumsum(target[order]) / target.sum()
    good = np.cumsum(~target[order]) / (~target).sum()
    return float(np.max(np.abs(bad - good)))


def shares_psi(expected, actual, floor: float = 1e-4) -> float:
    """PSI = Σ (факт − ожидание) × ln(факт / ожидание) по долям интервалов."""
    expected = np.clip(np.asarray(expected, dtype=float), floor, None)
    actual = np.clip(np.asarray(actual, dtype=float), floor, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def psi(expected, actual, bins: int = 10) -> float:
    """PSI распределения actual относительно expected; интервалы — децили expected.

    Принято: меньше 0.1 — стабильно, 0.1–0.25 — заметный сдвиг, больше 0.25 — сильный.
    """
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)[1:-1]))
    shares = [np.bincount(np.searchsorted(edges, v, side="right"), minlength=edges.size + 1) / v.size
              for v in (expected, actual)]
    return shares_psi(*shares)
