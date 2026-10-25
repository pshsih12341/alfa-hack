"""Сборка выборок: train, out-of-time test и партии с дрейфом."""
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from alfa_ml.config import deep_merge, load_config
from alfa_ml.metrics import gini
from alfa_ml.sources.export import export_database, sqlite_engine, write_postgres_init
from alfa_ml.synth import anomalies, risk
from alfa_ml.synth.applications import generate_applications
from alfa_ml.synth.flows import available_months, generate_monthly_flows
from alfa_ml.synth.ids import IdCounter, InnFactory
from alfa_ml.synth.population import generate_population, registry_events


@dataclass
class Batch:
    """Таблицы одной выборки. truth и labels — только для генерации и оценки, не для фич."""
    companies: pd.DataFrame
    persons: pd.DataFrame
    person_history: pd.DataFrame
    bankruptcy_cases: pd.DataFrame
    rfm_entries: pd.DataFrame
    bki_subjects: pd.DataFrame
    bki_inquiries: pd.DataFrame
    bki_loans: pd.DataFrame
    applications: pd.DataFrame
    monthly: pd.DataFrame
    truth: pd.DataFrame
    labels: pd.DataFrame

    @classmethod
    def concat(cls, batches: list["Batch"]) -> "Batch":
        return cls(**{f.name: pd.concat([getattr(b, f.name) for b in batches], ignore_index=True)
                      for f in fields(cls)})

    def write(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for f in fields(self):
            getattr(self, f.name).to_parquet(path / f"{f.name}.parquet", index=False)


@dataclass
class Segment:
    """Часть выборки с общими параметрами генерации."""
    size: int
    config: dict
    drift_type: str = ""          # пусто — обычные данные
    shock: dict | None = None     # падение поступлений: {"revenue": -0.15, "months": 4}
    intercept_shift: float = 0.0  # сдвиг закона риска


@dataclass
class Context:
    """Общее для всех выборок: конфиги и сквозные идентификаторы."""
    gen_cfg: dict
    scoring_cfg: dict
    inns: InnFactory
    app_ids: IdCounter
    loan_ids: IdCounter


def random_dates(rng: np.random.Generator, n: int, first: str, last: str) -> pd.DatetimeIndex:
    """Случайные дни между first и last: месяцами "2024-01" или датами "2026-11-01" включительно."""
    start = pd.Timestamp(first) if len(first) > 7 else pd.Period(first, "M").start_time
    end = pd.Timestamp(last) if len(last) > 7 else pd.Period(last, "M").end_time.normalize()
    days = (end - start).days + 1
    return pd.DatetimeIndex(start + pd.to_timedelta(rng.integers(0, days, n), unit="D")).normalize()


def generate_segment(segment: Segment, period: tuple[str, str], ctx: Context, rng: np.random.Generator) -> Batch:
    cfg, scoring = segment.config, ctx.scoring_cfg
    n = segment.size
    ids = ctx.app_ids.take(n)
    dates = random_dates(rng, n, *period)
    outliers = anomalies.plan_outliers(n, cfg, rng)
    pop = generate_population(ids, dates, cfg, scoring, rng, ctx.inns, ctx.loan_ids,
                              giant=outliers == "giant_company")

    comp = pop.companies
    months_count = available_months(dates, comp["registration_date"], cfg["flows"]["months"])
    from_alfa = comp["is_alfa_client"].to_numpy() & (months_count >= scoring["features"]["revenue_min_months"])
    declared_source = ~from_alfa & comp["fns_revenue"].isna().to_numpy()
    anomalies.retarget(outliers, "revenue_typo", declared_source, rng)
    anomalies.retarget(outliers, "duplicated_month", months_count >= 2, rng)
    reasons = anomalies.plan_stop_rules(comp, outliers, cfg, rng)
    anomalies.apply_stop_rules(pop, reasons, dates, scoring, rng)
    registry_events(pop, dates, rng)

    applications = generate_applications(ids, dates, pop, cfg, scoring, rng)
    monthly = generate_monthly_flows(pop, dates, cfg, rng, one_off=outliers == "one_off_contract",
                                     shocked=np.full(n, segment.shock is not None), shock=segment.shock or {})
    labels = pd.DataFrame({
        "application_id": ids,
        "drift_type": segment.drift_type,
        "outlier_type": outliers.astype(str),
        "heuristic_reason": reasons.astype(str),
        "intercept_shift": segment.intercept_shift,
    })
    return Batch(companies=pop.companies, persons=pop.persons, person_history=pop.person_history,
                 bankruptcy_cases=pop.bankruptcy_cases, rfm_entries=pop.rfm_entries, bki_subjects=pop.bki_subjects,
                 bki_inquiries=pop.bki_inquiries, bki_loans=pop.bki_loans, applications=applications,
                 monthly=monthly, truth=pop.truth, labels=labels)


def build_sample(segments: list[Segment], period: tuple[str, str], ctx: Context, seed: np.random.SeedSequence,
                 intercept: float | None = None) -> tuple[Batch, float]:
    """Выборка с дефолтами. Без intercept свободный член калибруется на ней под целевую долю дефолтов."""
    rng = np.random.default_rng(seed)
    batch = Batch.concat([generate_segment(s, period, ctx, rng) for s in segments])
    drivers = risk.risk_drivers(batch, ctx.gen_cfg, ctx.scoring_cfg)
    batch.labels["cycle_shift"] = risk.cycle_shift(batch.applications["application_date"], ctx.gen_cfg)
    drivers["base"] += (batch.labels["intercept_shift"] + batch.labels["cycle_shift"]).to_numpy()
    passed = (batch.labels["heuristic_reason"] == "").to_numpy()
    if intercept is None:
        intercept = risk.calibrate_intercept(drivers[passed], ctx.gen_cfg["target_default_rate"],
                                             ctx.gen_cfg, ctx.scoring_cfg)
    pd_true, rate = risk.true_pd(drivers, intercept, ctx.gen_cfg, ctx.scoring_cfg)
    # PD без скрытого шума: потолок качества для модели на наблюдаемых данных.
    observable = drivers.assign(base=drivers["base"] - ctx.gen_cfg["risk"]["latent_noise_sd"]
                                * batch.truth["latent"].to_numpy())
    batch.labels["rate"] = rate
    batch.labels["true_pd"] = pd_true
    batch.labels["observable_pd"] = risk.true_pd(observable, intercept, ctx.gen_cfg, ctx.scoring_cfg)[0]
    batch.labels["default_12m"] = rng.random(len(pd_true)) < pd_true
    anomalies.apply_data_errors(batch.applications, batch.monthly, batch.labels["outlier_type"].to_numpy(), rng)
    return batch, intercept


def summarize(name: str, batch: Batch) -> dict:
    labels = batch.labels
    passed = labels["heuristic_reason"] == ""
    return {
        "sample": name,
        "rows": len(labels),
        "default_rate": round(labels.loc[passed, "default_12m"].mean(), 4),
        "oracle_gini": round(gini(labels.loc[passed, "default_12m"], labels.loc[passed, "true_pd"]), 3),
        "observable_gini": round(gini(labels.loc[passed, "default_12m"], labels.loc[passed, "observable_pd"]), 3),
        "outliers": round((labels["outlier_type"] != "").mean(), 3),
        "stop_rules": round((~passed).mean(), 3),
        "drifted": round((labels["drift_type"] != "").mean(), 3),
        "ip_share": round((batch.companies["legal_form"] == "ip").mean(), 3),
        "young_share": round((batch.truth["age_months"] < 12).mean(), 3),
        "monthly_rows": len(batch.monthly),
    }


def build_all(out_dir: Path, mocks_dir: Path | None = None) -> pd.DataFrame:
    """Все выборки из config/generator.yaml; таблицы — parquet в out_dir/<выборка>/.

    Базы-моки (mocks.sqlite и mocks_postgres.sql) — в mocks_dir, по умолчанию в out_dir.
    """
    mocks_dir = mocks_dir or out_dir
    gen, scoring = load_config("generator"), load_config("scoring")
    samples = gen["samples"]
    drift = samples["drift"]
    root = np.random.SeedSequence(gen["seed"])
    inn_seed, train_seed, oot_seed, drift_seed, demo_seed = root.spawn(5)
    ctx = Context(gen, scoring, InnFactory(np.random.default_rng(inn_seed)), IdCounter(), IdCounter())

    summary = []
    train, intercept = build_sample([Segment(samples["train"]["size"], gen)], samples["train"]["months"],
                                     ctx, train_seed)
    train.write(out_dir / "train")
    summary.append(summarize("train", train))

    oot, _ = build_sample([Segment(samples["test_oot"]["size"], gen)], samples["test_oot"]["months"],
                          ctx, oot_seed, intercept)
    oot.write(out_dir / "test_oot")
    summary.append(summarize("test_oot", oot))

    seeds = iter(drift_seed.spawn(len(drift["scenarios"]) * len(drift["shares"])))
    month = drift["month"]
    for scenario in drift["scenarios"]:
        sc = gen["drift_scenarios"][scenario]
        shock = {"revenue": sc["revenue_shock"], "months": sc["shock_months"]} if "revenue_shock" in sc else None
        for share in drift["shares"]:
            drifted = int(round(drift["size"] * share))
            segments = [
                Segment(drift["size"] - drifted, gen),
                Segment(drifted, deep_merge(gen, sc.get("overrides", {})), scenario, shock, sc.get("intercept_shift", 0.0)),
            ]
            name = f"drift_{scenario}_{int(share * 100):02d}"
            batch, _ = build_sample(segments, (month, month), ctx, next(seeds), intercept)
            batch.write(out_dir / name)
            summary.append(summarize(name, batch))

    # Срез на дату демо — из него собираются базы-моки.
    demo = gen["demo"]
    demo_batch, _ = build_sample([Segment(demo["size"], gen)], (demo["as_of"], demo["as_of"]), ctx, demo_seed, intercept)
    demo_batch.write(out_dir / "demo")
    mocks_dir.mkdir(parents=True, exist_ok=True)
    engine = sqlite_engine(mocks_dir / "mocks.sqlite")
    export_database(demo_batch, engine)
    engine.dispose()
    write_postgres_init(demo_batch, mocks_dir / "mocks_postgres.sql")
    summary.append(summarize("demo", demo_batch))

    table = pd.DataFrame(summary)
    table.to_csv(out_dir / "summary.csv", index=False)
    (out_dir / "intercept.txt").write_text(f"{intercept:.6f}\n", encoding="utf-8")
    return table
