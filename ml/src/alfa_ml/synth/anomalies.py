"""Выбросы и отказы по эвристикам (стоп-правила).

Реальные выбросы (крупный разовый контракт, очень крупная компания) создаются до расчёта
истинного риска и влияют на него. Ошибки данных (опечатка в выручке, задвоенный месяц)
вносятся после: настоящий риск компании от них не меняется.
"""
import numpy as np
import pandas as pd

from alfa_ml.synth.population import Population, months_before


def plan_outliers(n: int, cfg: dict, rng: np.random.Generator) -> np.ndarray:
    """Тип выброса для каждой строки; пустая строка — обычные данные."""
    a = cfg["anomalies"]
    types = np.full(n, "", dtype=object)
    count = int(round(a["outlier_share"] * n))
    names = list(a["outlier_types"])
    probs = np.array(list(a["outlier_types"].values()), dtype=float)
    types[rng.choice(n, size=count, replace=False)] = rng.choice(names, size=count, p=probs / probs.sum())
    return types


def retarget(types: np.ndarray, kind: str, eligible: np.ndarray, rng: np.random.Generator) -> None:
    """Переносит выбросы типа kind на строки, где они что-то меняют.

    Опечатка в анкетной выручке ни на что не влияет, если выручка взята из Альфы или ФНС.
    """
    wrong = np.flatnonzero((types == kind) & ~eligible)
    free = np.flatnonzero((types == "") & eligible)
    take = min(wrong.size, free.size)
    types[wrong[:take]] = ""
    types[rng.choice(free, size=take, replace=False)] = kind


def plan_stop_rules(companies: pd.DataFrame, outliers: np.ndarray, cfg: dict, rng: np.random.Generator) -> np.ndarray:
    """Какое стоп-правило сработает у строки; пустая строка — ни одно."""
    a = cfg["anomalies"]
    n = len(companies)
    count = int(round(a["stop_rule_share"] * n))
    reasons = np.full(n, "", dtype=object)
    names = list(a["stop_rule_types"])
    probs = np.array(list(a["stop_rule_types"].values()), dtype=float)
    rows = rng.choice(np.flatnonzero(outliers == ""), size=count, replace=False)
    reasons[rows] = rng.choice(names, size=count, p=probs / probs.sum())
    # Процедура банкротства компании есть только у юрлица; у ИП это банкротство его самого.
    ip = (companies["legal_form"] == "ip").to_numpy()
    reasons[(reasons == "company_bankruptcy") & ip] = "owner_bankruptcy"
    return reasons


def apply_stop_rules(pop: Population, reasons: np.ndarray, app_dates: pd.DatetimeIndex, scoring_cfg: dict,
                     rng: np.random.Generator) -> None:
    """Меняет данные реестров так, чтобы сработало запланированное стоп-правило."""
    comp, persons = pop.companies, pop.persons
    ip = (comp["legal_form"] == "ip").to_numpy()

    inactive = reasons == "inactive_status"
    comp.loc[inactive & ip, "status"] = "ceased"
    comp.loc[inactive & ~ip, "status"] = rng.choice(["liquidating", "reorganizing", "excluded"],
                                                    size=int((inactive & ~ip).sum()))
    comp.loc[reasons == "company_bankruptcy", "bankruptcy_procedure"] = True

    # Банкротство ИП или директора ООО завершилось внутри окна запрета.
    rules = scoring_cfg["stop_rules"]
    app_date = pd.Series(app_dates, index=comp["application_id"])
    is_ip = pd.Series(ip, index=comp["application_id"])
    bankrupt_apps = comp.loc[reasons == "owner_bankruptcy", "application_id"]
    target = persons["application_id"].isin(bankrupt_apps) & persons["is_director"]
    target_apps = persons.loc[target, "application_id"]
    window = np.where(is_ip.loc[target_apps].to_numpy(), rules["ip_bankruptcy_months"], rules["director_bankruptcy_months"])
    persons.loc[target, "bankruptcy_end_date"] = months_before(
        pd.DatetimeIndex(app_date.loc[target_apps].to_numpy()), rng.uniform(1, window - 1)).to_numpy()

    # Перечень Росфинмониторинга: ИП сам; у ООО — сама компания или директор.
    listed = reasons == "rfm_list"
    company_listed = listed & ~ip & (rng.random(len(comp)) < 0.5)
    comp.loc[company_listed, "in_rfm_list"] = True
    person_apps = comp.loc[listed & ~company_listed, "application_id"]
    persons.loc[persons["application_id"].isin(person_apps) & persons["is_director"], "in_rfm_list"] = True


def apply_data_errors(applications: pd.DataFrame, monthly: pd.DataFrame, types: np.ndarray,
                      rng: np.random.Generator) -> None:
    """Опечатка в анкетной выручке (×1000 или ÷1000) и задвоенный месяц в выписке."""
    typo = types == "revenue_typo"
    factor = np.where(rng.random(int(typo.sum())) < 0.5, 1000.0, 0.001)
    applications.loc[typo, "declared_revenue"] = np.round(applications.loc[typo, "declared_revenue"] * factor, -3)

    duplicated = applications.loc[types == "duplicated_month", "application_id"]
    candidates = monthly[monthly["application_id"].isin(duplicated)]
    if len(candidates):
        rows = candidates.groupby("application_id").sample(1, random_state=rng).index
        money = [col for col in monthly.columns if col not in ("application_id", "month")]
        monthly.loc[rows, money] = monthly.loc[rows, money] * 2
