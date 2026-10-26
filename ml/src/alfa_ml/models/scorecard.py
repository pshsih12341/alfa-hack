"""Скоркарта: WoE-биннинг фич и логистическая регрессия на WoE. Хранится в JSON, сервису нужен только этот модуль.

PD = 1 / (1 + exp(−(intercept + Σ коэффициент × WoE фичи))).
"""
import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from alfa_ml.artifacts import ARTIFACTS_DIR
from alfa_ml.models.woe import Binning

MODEL1_FILE = "model1.json"
MODEL2_FILE = "model2.json"


@dataclass
class Scorecard:
    version: str
    intercept: float
    coefficients: dict[str, float]
    binnings: dict[str, Binning]
    info: dict = field(default_factory=dict)  # выборка, метрики, отбор фич — для отчёта

    def woe_matrix(self, x: pd.DataFrame) -> np.ndarray:
        return np.column_stack([self.binnings[name].transform(x[name]) for name in self.coefficients])

    def logit(self, x: pd.DataFrame) -> np.ndarray:
        return self.intercept + self.woe_matrix(x) @ np.array(list(self.coefficients.values()))

    def predict_pd(self, x: pd.DataFrame) -> np.ndarray:
        return 1 / (1 + np.exp(-self.logit(x)))

    def save(self, path: Path) -> None:
        payload = {
            "version": self.version,
            "intercept": self.intercept,
            "coefficients": self.coefficients,
            "binnings": {name: self.binnings[name].to_dict() for name in self.coefficients},
            "info": self.info,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Scorecard":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(version=data["version"], intercept=data["intercept"], coefficients=data["coefficients"],
                   binnings={name: Binning.from_dict(b) for name, b in data["binnings"].items()},
                   info=data.get("info", {}))


@cache
def load_model(file_name: str, directory: Path = ARTIFACTS_DIR) -> Scorecard:
    """Обученная модель из ml/artifacts (читается один раз)."""
    return Scorecard.load(directory / file_name)
