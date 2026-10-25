"""Демо-сценарии: какие ИНН из баз-моков при каких условиях дают какое решение этапа 1.

Запуск из ml/: uv run python -m alfa_ml.scenarios --db sqlite:///../mocks/mocks.sqlite --demo ../mocks/datasets/demo
Решение зависит от ИНН, суммы, срока и (если выручки нет в источниках) от выручки из анкеты.
Список считается тем же кодом, что и POST /score, — после смены модели его нужно пересобрать.
"""
import argparse
from pathlib import Path

import pandas as pd

from alfa_ml.config import load_config
from alfa_ml.decision.stage1 import Application, RevenueRequired, decide_stage1
from alfa_ml.features.build import revenue_source
from alfa_ml.service.db import make_engine, snapshot_date
from alfa_ml.sources.read import read_sources


def _rub(value) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _option(option) -> str:
    return f"{_rub(option.credit_sum)} ₽ / {option.term_months} мес / {option.rate:.0%}"


def collect(db_url: str, demo_dir: Path) -> pd.DataFrame:
    """Решение по каждой заявке демо-среза с её суммой и сроком; цель — пополнение оборотных средств."""
    scoring, rules = load_config("scoring"), load_config("rules")
    apps = pd.read_parquet(demo_dir / "applications.parquet")
    apps = apps[apps["requested_amount"].between(scoring["min_amount"], scoring["max_amount"])]
    engine = make_engine(db_url)
    rows = []
    with engine.connect() as conn:
        as_of = snapshot_date(conn)
        for _, app_row in apps.iterrows():
            src = read_sources(conn, app_row["inn"], as_of,
                               inquiries_window_days=scoring["features"]["inquiries_window_days"])
            org = src.companies.iloc[0]
            source = revenue_source([org["is_alfa_client"]], [len(src.monthly)], [org["fns_revenue"]],
                                    scoring["features"]["revenue_min_months"])[0]
            known = source != "declared"
            revenue = None if known or app_row["declared_revenue"] <= 0 else float(app_row["declared_revenue"])
            application = Application(int(app_row["requested_amount"]), int(app_row["term_months"]),
                                      "working_capital", (), revenue)
            try:
                decision = decide_stage1(src, application, as_of, scoring, rules)
            except RevenueRequired:
                continue
            maxima = dict(decision.max_by_term)
            at_term = maxima.get(application.term_months)
            if decision.decision == "APPROVED":
                detail = f"одобрено {_option(decision.approved)}; на этом сроке — до {_rub(at_term.credit_sum)} ₽"
            elif decision.decision == "OFFER":
                detail = "варианты: " + "; ".join(_option(o) for o in decision.offers)
            elif decision.stop_rules:
                detail = "стоп-правило " + ", ".join(decision.stop_rules)
            elif decision.decision == "REJECTED":
                detail = f"PD {decision.pd:.0%} выше порога отказа"
            else:
                detail = f"нужны выписки ({'данные счёта' if org['is_alfa_client'] else 'файлы'}), PD {decision.pd:.0%}"
            rows.append({
                "decision": decision.decision, "inn": org["inn"], "name": org["name"], "legal_form": org["legal_form"],
                "revenue_known": known, "credit_sum": application.credit_sum, "term_months": application.term_months,
                "revenue_last12m": revenue, "pd": decision.pd, "stop_rules": ",".join(decision.stop_rules),
                "offers": len(decision.offers), "detail": detail,
            })
    engine.dispose()
    return pd.DataFrame(rows)


def pick(scenarios: pd.DataFrame, per_outcome: int) -> pd.DataFrame:
    """Наглядные примеры: сначала ИНН, где выручка уже есть в источниках (форма её не спросит), ИП и ООО вперемешку;
    для отказов — по одному на каждое стоп-правило и несколько отказов по PD."""
    known_first = scenarios.sort_values(["revenue_known", "legal_form"], ascending=[False, True])
    picked = []
    for decision in ["APPROVED", "OFFER", "INFO"]:
        pool = known_first[known_first["decision"] == decision]
        if decision == "OFFER":
            pool = pool.sort_values("offers", ascending=False, kind="stable")
        by_form = [pool[pool["legal_form"] == form].head((per_outcome + 1) // 2) for form in ("ooo", "ip")]
        picked.append(pd.concat(by_form).head(per_outcome))
    rejected = known_first[known_first["decision"] == "REJECTED"]
    picked.append(rejected[rejected["stop_rules"] != ""].drop_duplicates("stop_rules"))
    picked.append(rejected[rejected["stop_rules"] == ""].head(2))
    return pd.concat(picked, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Демо-сценарии этапа 1 по базам-мокам")
    parser.add_argument("--db", default="sqlite:///../mocks/mocks.sqlite", help="строка подключения к базам-мокам")
    parser.add_argument("--demo", type=Path, default=Path("../mocks/datasets/demo"), help="папка демо-среза")
    parser.add_argument("--per-outcome", type=int, default=5)
    args = parser.parse_args()
    scenarios = collect(args.db, args.demo)
    print("Всего заявок:", len(scenarios), "| доли решений:",
          scenarios["decision"].value_counts(normalize=True).round(3).to_dict())
    for _, row in pick(scenarios, args.per_outcome).iterrows():
        revenue = "из источников" if row["revenue_known"] else f"выручка {_rub(row['revenue_last12m'])} ₽"
        print(f"{row['decision']:9s} | {row['inn']} | {row['legal_form']} | {row['name']} | "
              f"{_rub(row['credit_sum'])} ₽ на {row['term_months']} мес | {revenue} | {row['detail']}")


if __name__ == "__main__":
    main()
