"""Артефакты модели: то, что оценивается на обучающей выборке и нужно сервису при скоринге.

Лежат в ml/artifacts (или в ALFA_ML_ARTIFACTS_DIR), попадают в образ сервиса.
Пересборка из ml/: uv run python -m alfa_ml.artifacts --train ../mocks/datasets/train
"""
import argparse
import json
import os
from pathlib import Path

import pandas as pd

from alfa_ml.config import load_config
from alfa_ml.features.build import okved_group
from alfa_ml.features.statements import seasonal_index

ARTIFACTS_DIR = Path(os.environ.get("ALFA_ML_ARTIFACTS_DIR", Path(__file__).resolve().parents[2] / "artifacts"))
SEASONALITY_FILE = "seasonality.json"


def load_seasonality(scoring_cfg: dict, directory: Path = ARTIFACTS_DIR) -> pd.DataFrame:
    """Сезонный индекс групп ОКВЭД; если артефакта нет — без поправок (все месяцы 1.0)."""
    groups = list(scoring_cfg["okved_groups"])
    table = pd.DataFrame(1.0, index=groups, columns=range(1, 13))
    path = directory / SEASONALITY_FILE
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))["index"]
        for group, values in stored.items():
            if group in table.index:
                table.loc[group] = values
    return table


def build_seasonality(train_dir: Path, scoring_cfg: dict) -> pd.DataFrame:
    companies = pd.read_parquet(train_dir / "companies.parquet", columns=["application_id", "okved_code"])
    monthly = pd.read_parquet(train_dir / "monthly.parquet")
    groups = okved_group(companies.set_index("application_id")["okved_code"], scoring_cfg["okved_groups"])
    return seasonal_index(monthly, groups, list(scoring_cfg["okved_groups"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересборка артефактов модели по обучающей выборке")
    parser.add_argument("--train", type=Path, default=Path("../mocks/datasets/train"))
    args = parser.parse_args()
    scoring = load_config("scoring")
    table = build_seasonality(args.train, scoring)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"description": "Сезонный индекс поступлений по группам ОКВЭД: месяцы 1–12, среднее по строке 1. "
                              "Оценён по компаниям train с полным годом выписок.",
               "index": {group: [round(float(v), 4) for v in row] for group, row in table.iterrows()}}
    (ARTIFACTS_DIR / SEASONALITY_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(table.round(2).to_string())


if __name__ == "__main__":
    main()
