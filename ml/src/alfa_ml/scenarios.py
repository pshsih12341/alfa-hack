"""Демо-сценарии: какие ИНН из баз-моков при каких условиях дают какое решение этапов 1 и 2.

Запуск из ml/: uv run python -m alfa_ml.scenarios --db sqlite:///../mocks/mocks.sqlite --demo ../mocks/datasets/demo
С --files для ИНН из списка, которым на этапе 2 нужны файлы выписок, пишутся файлы 1С в ../mocks/statements.
Решение зависит от ИНН, суммы, срока, цели, залога и (если выручки нет в источниках) от выручки из анкеты.
Список считается тем же кодом, что и POST /score, — после смены модели его нужно пересобрать.
"""
import argparse
from pathlib import Path

import pandas as pd

from alfa_ml.artifacts import load_seasonality
from alfa_ml.config import load_config
from alfa_ml.decision.stage1 import Application, RevenueRequired, decide_stage1, percent
from alfa_ml.decision.stage2 import decide_stage2
from alfa_ml.features.build import revenue_source
from alfa_ml.service.db import make_engine, snapshot_date
from alfa_ml.sources.read import read_sources
from alfa_ml.synth.onec_files import statement_file


def _rub(value) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _option(option) -> str:
    return f"{_rub(option.credit_sum)} ₽ / {option.term_months} мес / {percent(option.rate)}"


def _purpose(row) -> str:
    text = row["purpose"] + (f" (кредиты {row['refinance_loan_ids']})" if row["refinance_loan_ids"] else "")
    return text + (", с залогом" if row["has_collateral"] else "")


def _detail(decision, org, at_term) -> str:
    if decision.decision == "APPROVED":
        return f"одобрено {_option(decision.approved)}; на этом сроке — до {_rub(at_term.credit_sum)} ₽"
    if decision.decision == "OFFER":
        return "варианты: " + "; ".join(_option(o) for o in decision.offers)
    if decision.stop_rules:
        return "стоп-правило " + ", ".join(decision.stop_rules)
    if decision.decision == "REJECTED":
        if decision.pd is None:  # не хватает месяцев выписок
            return decision.reasons[-1]
        if decision.stage == 1:
            return f"PD {decision.pd:.0%} выше порога отказа"
        dscr = next(r for r in decision.reasons if r.startswith("DSCR"))
        return f"PD {decision.pd:.0%}; {dscr} — ни один вариант не проходит"
    return f"нужны выписки ({'данные счёта' if org['is_alfa_client'] else 'файлы'}), PD {decision.pd:.0%}"


def collect(db_url: str, demo_dir: Path) -> pd.DataFrame:
    """Решение по каждой заявке демо-среза с её суммой, сроком, целью и залогом.
    Для INFO — ещё и решение этапа 2: по счёту в Альфе или по файлам с оборотами из демо-среза."""
    scoring, rules = load_config("scoring"), load_config("rules")
    seasonality = load_seasonality(scoring)
    apps = pd.read_parquet(demo_dir / "applications.parquet")
    apps = apps[apps["requested_amount"].between(scoring["min_amount"], scoring["max_amount"])]
    statements = pd.read_parquet(demo_dir / "monthly.parquet")
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
                                      app_row["purpose"], tuple(int(i) for i in app_row["refinance_loan_ids"]),
                                      revenue, bool(app_row["has_collateral"]))
            try:
                decision = decide_stage1(src, application, as_of, scoring, rules)
            except RevenueRequired:
                continue
            stage2, stage2_detail = "", ""
            if decision.decision == "INFO":
                monthly = src.monthly if org["is_alfa_client"] else \
                    statements[statements["application_id"] == app_row["application_id"]]
                second = decide_stage2(src, monthly, application, as_of, scoring, rules, seasonality)
                stage2 = second.decision
                stage2_detail = _detail(second, org, dict(second.max_by_term).get(application.term_months))
            rows.append({
                "decision": decision.decision, "inn": org["inn"], "name": org["name"], "legal_form": org["legal_form"],
                "application_id": app_row["application_id"], "is_alfa_client": bool(org["is_alfa_client"]),
                "revenue_known": known, "credit_sum": application.credit_sum, "term_months": application.term_months,
                "purpose": application.purpose, "has_collateral": application.has_collateral,
                "refinance_loan_ids": ",".join(map(str, application.refinance_loan_ids)),
                "revenue_last12m": revenue, "pd": decision.pd, "stop_rules": ",".join(decision.stop_rules),
                "offers": len(decision.offers),
                "detail": _detail(decision, org, dict(decision.max_by_term).get(application.term_months)),
                "stage2": stage2, "stage2_detail": stage2_detail,
            })
    engine.dispose()
    return pd.DataFrame(rows)


def pick(scenarios: pd.DataFrame, per_outcome: int) -> pd.DataFrame:
    """Наглядные примеры: сначала ИНН, где выручка уже есть в источниках (форма её не спросит), ИП и ООО вперемешку;
    для отказов — по одному на каждое стоп-правило и несколько отказов по PD."""
    known_first = scenarios.sort_values(["revenue_known", "legal_form"], ascending=[False, True])
    picked = []
    for decision in ["APPROVED", "OFFER"]:
        pool = known_first[known_first["decision"] == decision]
        if decision == "OFFER":
            pool = pool.sort_values("offers", ascending=False, kind="stable")
        by_form = [pool[pool["legal_form"] == form].head((per_outcome + 1) // 2) for form in ("ooo", "ip")]
        picked.append(pd.concat(by_form).head(per_outcome))
    # INFO — по каждому исходу этапа 2, и по счёту в Альфе, и по файлам.
    info = known_first[known_first["decision"] == "INFO"]
    picked.append(info.drop_duplicates(["stage2", "is_alfa_client"]))
    rejected = known_first[known_first["decision"] == "REJECTED"]
    picked.append(rejected[rejected["stop_rules"] != ""].drop_duplicates("stop_rules"))
    picked.append(rejected[rejected["stop_rules"] == ""].head(2))
    return pd.concat(picked, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Демо-сценарии этапа 1 по базам-мокам")
    parser.add_argument("--db", default="sqlite:///../mocks/mocks.sqlite", help="строка подключения к базам-мокам")
    parser.add_argument("--demo", type=Path, default=Path("../mocks/datasets/demo"), help="папка демо-среза")
    parser.add_argument("--per-outcome", type=int, default=5)
    parser.add_argument("--files", type=Path, default=None,
                        help="куда писать файлы 1С для ИНН из списка, которым на этапе 2 нужны выписки файлами")
    args = parser.parse_args()
    scenarios = collect(args.db, args.demo)
    print("Всего заявок:", len(scenarios), "| доли решений:",
          scenarios["decision"].value_counts(normalize=True).round(3).to_dict())
    info = scenarios[scenarios["decision"] == "INFO"]
    print("Этап 2 для INFO:", info["stage2"].value_counts(normalize=True).round(3).to_dict())
    picked = pick(scenarios, args.per_outcome)
    for _, row in picked.iterrows():
        revenue = "из источников" if row["revenue_known"] else f"выручка {_rub(row['revenue_last12m'])} ₽"
        line = (f"{row['decision']:9s} | {row['inn']} | {row['legal_form']} | {row['name']} | "
                f"{_rub(row['credit_sum'])} ₽ на {row['term_months']} мес | {_purpose(row)} | {revenue} | {row['detail']}")
        if row["stage2"]:
            source = "useAlfaAccount" if row["is_alfa_client"] else f"файл {row['inn']}.txt"
            line += f" → этап 2 ({source}): {row['stage2']}, {row['stage2_detail']}"
        print(line)
    if args.files:
        write_files(picked[(picked["decision"] == "INFO") & ~picked["is_alfa_client"]], args.demo, args.files)


def write_files(rows: pd.DataFrame, demo_dir: Path, out_dir: Path) -> None:
    """Файлы 1С с оборотами из демо-среза — их загружают на этапе 2 вместо выписки из банка."""
    persons = pd.read_parquet(demo_dir / "persons.parquet")
    monthly = pd.read_parquet(demo_dir / "monthly.parquet")
    as_of = pd.read_parquet(demo_dir / "applications.parquet")["application_date"].iloc[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    for _, row in rows.iterrows():
        director = persons[(persons["application_id"] == row["application_id"]) & persons["is_director"]].iloc[0]
        content = statement_file(monthly[monthly["application_id"] == row["application_id"]], row["inn"],
                                 row["name"], row["legal_form"], {"inn": director["inn"], "name": director["name"]},
                                 as_of)
        (out_dir / f"{row['inn']}.txt").write_bytes(content)
        print(f"файл: {out_dir / (row['inn'] + '.txt')}")


if __name__ == "__main__":
    main()
