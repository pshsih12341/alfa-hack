"""Обучение моделей 1 и 2: WoE-биннинг + логистическая регрессия.

Запуск из ml/: uv run python -m alfa_ml.models.train --data ../mocks/datasets
Пишет в ml/artifacts model1.json и model2.json, а в model_report.json — метрики на train, test_oot
и выборках с дрейфом, IV и итоги отбора фич. Параметры — config/training.yaml.

Отбор фич:
1. Биннинг всех фич модели на train, IV каждой. IV меньше min_iv — фича исключается.
2. Из пары фич с корреляцией WoE больше max_correlation остаётся фича с большим IV.
3. Логистическая регрессия на WoE. Коэффициент ≤ 0 значит, что фича работает против собственного WoE
   (обычно из-за коллинеарности); p-value больше max_p_value — вклад не отличить от шума.
   Такие фичи исключаются по одной, и модель обучается заново.
Фичи из forced не исключаются по IV, корреляции и p-value — только по знаку коэффициента.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from alfa_ml.artifacts import ARTIFACTS_DIR, load_seasonality
from alfa_ml.config import load_config
from alfa_ml.decision import heuristic
from alfa_ml.decision.stage1 import flat_seasonality
from alfa_ml.features.build import model1_features, model2_features, profile
from alfa_ml.metrics import gini, ks, psi, shares_psi
from alfa_ml.models.scorecard import MODEL1_FILE, MODEL2_FILE, Scorecard
from alfa_ml.models.woe import Binning, fit_categorical, fit_numeric

SAMPLE_TABLES = ["applications", "companies", "persons", "bki_subjects", "bki_loans", "monthly", "labels"]
REPORT_FILE = "model_report.json"


def load_sample(directory: Path) -> SimpleNamespace:
    return SimpleNamespace(**{name: pd.read_parquet(directory / f"{name}.parquet") for name in SAMPLE_TABLES})


def stage1_dataset(sample, scoring_cfg: dict) -> tuple[pd.DataFrame, pd.Series]:
    """Фичи модели 1 и дефолты заявок без стоп-правил. Выписки на этапе 1 есть только у клиентов Альфы."""
    alfa = sample.companies.loc[sample.companies["is_alfa_client"], "application_id"]
    data = SimpleNamespace(**vars(sample))
    data.monthly = sample.monthly[sample.monthly["application_id"].isin(alfa)]
    prof = profile(data, scoring_cfg, flat_seasonality(scoring_cfg))
    apps = sample.applications.set_index("application_id").loc[prof.index]
    x = model1_features(prof, apps["requested_amount"])
    labels = sample.labels.set_index("application_id").loc[prof.index]
    keep = (labels["heuristic_reason"] == "").to_numpy()
    return x[keep], labels.loc[keep, "default_12m"].astype(int)


def stage2_dataset(sample, scoring_cfg: dict, seasonality: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Фичи модели 2 и дефолты заявок без стоп-правил, у которых хватает месяцев выписок.
    Платёж в DSCR — по фактической ставке кредита."""
    prof = profile(sample, scoring_cfg, seasonality)
    apps = sample.applications.set_index("application_id").loc[prof.index]
    labels = sample.labels.set_index("application_id").loc[prof.index]
    x = model2_features(prof, apps["requested_amount"], apps["term_months"], labels["rate"])
    enough = prof["statement_months"] >= scoring_cfg["stage2"]["min_statement_months"]
    keep = ((labels["heuristic_reason"] == "") & enough).to_numpy()
    return x[keep], labels.loc[keep, "default_12m"].astype(int)


def fit_logistic(w: np.ndarray, y: np.ndarray, iterations: int = 100) -> tuple[float, np.ndarray, np.ndarray]:
    """Логистическая регрессия методом Ньютона: свободный член, коэффициенты и их стандартные ошибки."""
    a = np.column_stack([np.ones(len(y)), w])
    beta = np.zeros(a.shape[1])
    beta[0] = np.log(y.mean() / (1 - y.mean()))
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-a @ beta))
        hessian = a.T @ (a * (p * (1 - p))[:, None])
        step = np.linalg.solve(hessian, a.T @ (y - p))
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    se = np.sqrt(np.diag(np.linalg.inv(hessian)))
    return float(beta[0]), beta[1:], se[1:]


def fit_binnings(x: pd.DataFrame, y: pd.Series, cfg: dict) -> dict[str, Binning]:
    b, directions = cfg["binning"], cfg["directions"]
    neutral = set(cfg["binning"]["neutral_missing"])
    return {name: fit_numeric(name, x[name], y, directions[name], b["min_bin_share"], b["max_bins"], b["prebins"],
                              b["missing_min_share"], name in neutral)
            if name in directions
            else fit_categorical(name, x[name], y, b["min_bin_share"], b["max_bins"], b["missing_min_share"])
            for name in x.columns}


def train_scorecard(x: pd.DataFrame, y: pd.Series, cfg: dict, version: str) -> Scorecard:
    sel = cfg["selection"]
    forced = set(sel["forced"])
    binnings = fit_binnings(x, y, cfg)
    woe = pd.DataFrame({name: b.transform(x[name]) for name, b in binnings.items()}, index=x.index)
    dropped: dict[str, str] = {}
    kept: list[str] = []
    for name in sorted(binnings, key=lambda n: binnings[n].iv, reverse=True):
        iv = binnings[name].iv
        if iv < sel["min_iv"] and name not in forced:
            dropped[name] = f"IV {iv:.3f} меньше {sel['min_iv']}"
            continue
        correlations = {k: abs(np.corrcoef(woe[name], woe[k])[0, 1]) for k in kept}
        partner = next((k for k, r in correlations.items() if r > sel["max_correlation"]), None)
        if partner and name not in forced:
            dropped[name] = f"корреляция WoE с {partner} {correlations[partner]:.2f}"
            continue
        kept.append(name)

    target = y.to_numpy(dtype=float)
    while True:
        intercept, coef, se = fit_logistic(woe[kept].to_numpy(), target)
        p_values = [math.erfc(abs(c / s) / math.sqrt(2)) for c, s in zip(coef, se)]
        wrong_sign = [i for i, c in enumerate(coef) if c <= 0]
        weak = [i for i, p in enumerate(p_values) if p > sel["max_p_value"] and kept[i] not in forced]
        if wrong_sign:
            i = min(wrong_sign, key=lambda k: coef[k])
            dropped[kept[i]] = f"коэффициент {coef[i]:.2f} не больше 0"
        elif weak:
            i = max(weak, key=lambda k: p_values[k])
            dropped[kept[i]] = f"p-value {p_values[i]:.3f} больше {sel['max_p_value']}"
        else:
            break
        kept.pop(i)

    fitted = dict(zip(kept, zip(coef, se, p_values)))
    features = []
    for name, b in sorted(binnings.items(), key=lambda item: item[1].iv, reverse=True):
        row = {"name": name, "iv": round(b.iv, 4), "bins": len(b.woe), "selected": name in fitted}
        if name in fitted:
            c, s, p = fitted[name]
            row |= {"coefficient": round(float(c), 4), "std_error": round(float(s), 4), "p_value": float(f"{p:.3g}")}
        else:
            row["reason"] = dropped[name]
        features.append(row)
    return Scorecard(version=version, intercept=round(intercept, 6),
                     coefficients={name: round(float(c), 6) for name, (c, _, _) in fitted.items()},
                     binnings={name: binnings[name] for name in kept},
                     info={"features": features, "train_rows": int(len(y)), "train_default_rate": round(float(y.mean()), 4)})


def evaluate(model: Scorecard, x: pd.DataFrame, y: pd.Series, reference: np.ndarray | None = None) -> dict:
    """Качество на выборке; с reference (PD на train) — ещё и PSI распределения PD."""
    pd_values = model.predict_pd(x)
    result = {"rows": int(len(y)), "default_rate": round(float(y.mean()), 4),
              "mean_pd": round(float(pd_values.mean()), 4), "gini": round(gini(y, pd_values), 3),
              "ks": round(ks(y, pd_values), 3)}
    if reference is not None:
        result["score_psi"] = round(psi(reference, pd_values), 4)
    return result


def feature_psi(model: Scorecard, x_train: pd.DataFrame, x: pd.DataFrame) -> dict[str, float]:
    """PSI каждой фичи модели по её интервалам WoE."""
    result = {}
    for name, b in model.binnings.items():
        expected = pd.Series(b.bin_index(x_train[name])).value_counts(normalize=True)
        actual = pd.Series(b.bin_index(x[name])).value_counts(normalize=True)
        index = expected.index.union(actual.index)
        result[name] = round(shares_psi(expected.reindex(index, fill_value=0), actual.reindex(index, fill_value=0)), 4)
    return dict(sorted(result.items(), key=lambda item: item[1], reverse=True))


def calibration(model: Scorecard, x: pd.DataFrame, y: pd.Series, groups: int = 10) -> list[dict]:
    """Средний PD и доля дефолтов по децилям PD."""
    pd_values = model.predict_pd(x)
    decile = pd.qcut(pd.Series(pd_values).rank(method="first"), groups, labels=False)
    table = pd.DataFrame({"decile": decile + 1, "pd": pd_values, "default": y.to_numpy()}).groupby("decile")
    return [{"decile": int(d), "rows": int(len(g)), "mean_pd": round(float(g["pd"].mean()), 4),
             "default_rate": round(float(g["default"].mean()), 4)} for d, g in table]


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение моделей 1 и 2 (WoE + логистическая регрессия)")
    parser.add_argument("--data", type=Path, default=Path("../mocks/datasets"), help="папка с выборками генератора")
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR, help="куда писать модели и отчёт")
    args = parser.parse_args()
    scoring, cfg = load_config("scoring"), load_config("training")
    seasonality = load_seasonality(scoring)
    date = dt.date.today().strftime("%Y.%m.%d")
    names = ["train", "test_oot"] + sorted(p.name for p in args.data.iterdir() if p.name.startswith("drift_"))
    samples = {name: load_sample(args.data / name) for name in names}
    stages = {
        1: (MODEL1_FILE, lambda s: stage1_dataset(s, scoring), heuristic.predict_pd),
        2: (MODEL2_FILE, lambda s: stage2_dataset(s, scoring, seasonality), heuristic.predict_pd2),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    report = {}
    for stage, (file_name, dataset, expert) in stages.items():
        data = {name: dataset(sample) for name, sample in samples.items()}
        x_train, y_train = data["train"]
        model = train_scorecard(x_train, y_train, cfg, f"stage{stage}-woe-lr-{date}")
        reference = model.predict_pd(x_train)
        metrics = {}
        for name, (x, y) in data.items():
            metrics[name] = evaluate(model, x, y, None if name == "train" else reference)
            metrics[name]["expert_gini"] = round(gini(y, expert(x)), 3)
            if name.startswith("drift_"):
                metrics[name]["feature_psi"] = dict(list(feature_psi(model, x_train, x).items())[:3])
        model.info |= {"metrics": {name: metrics[name] for name in ("train", "test_oot")},
                       "calibration_test_oot": calibration(model, *data["test_oot"])}
        model.save(args.out / file_name)
        report[f"model{stage}"] = {"version": model.version, "intercept": model.intercept, **model.info,
                                   "metrics": metrics}
        _print(stage, model, metrics)
    (args.out / REPORT_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def _print(stage: int, model: Scorecard, metrics: dict) -> None:
    print(f"\n=== Модель {stage}: {model.version}, свободный член {model.intercept:.4f}")
    for row in model.info["features"]:
        if row["selected"]:
            detail = f"коэф. {row['coefficient']:.3f} (p {row['p_value']:.2g}), интервалов {row['bins']}"
        else:
            detail = "исключена: " + row["reason"]
        print(f"  {row['name']:22s} IV {row['iv']:.3f}  {detail}")
    print(f"  {'выборка':28s} {'строк':>6s} {'дефолты':>8s} {'ср. PD':>7s} {'Gini':>6s} {'KS':>6s} {'PSI':>6s} {'эксперт':>8s}")
    for name, m in metrics.items():
        print(f"  {name:28s} {m['rows']:6d} {m['default_rate']:8.2%} {m['mean_pd']:7.2%} {m['gini']:6.3f} "
              f"{m['ks']:6.3f} {m.get('score_psi', 0):6.3f} {m['expert_gini']:8.3f}"
              + (f"  {m['feature_psi']}" if "feature_psi" in m else ""))


if __name__ == "__main__":
    main()
