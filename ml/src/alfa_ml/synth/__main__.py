"""Генерация синтетических выборок: uv run python -m alfa_ml.synth --out data/synth --mocks ../mocks"""
import argparse
from pathlib import Path

from alfa_ml.synth.datasets import build_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация синтетических выборок для ML-части")
    parser.add_argument("--out", type=Path, default=Path("data/synth"), help="куда сохранить parquet-файлы")
    parser.add_argument("--mocks", type=Path, default=None,
                        help="куда сохранить базы-моки (mocks.sqlite, mocks_postgres.sql); по умолчанию — в --out")
    args = parser.parse_args()
    summary = build_all(args.out, args.mocks)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
