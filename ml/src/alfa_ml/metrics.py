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
