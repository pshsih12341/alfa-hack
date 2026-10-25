"""Профили компаний, собственники, кредитная история и налоги."""
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from alfa_ml.finance import annuity_payment
from alfa_ml.sources.read import BAD_OUTCOMES
from alfa_ml.synth.ids import IdCounter, InnFactory, company_names, person_names

DAYS_PER_MONTH = 30.4375


@dataclass
class Population:
    companies: pd.DataFrame
    persons: pd.DataFrame
    person_history: pd.DataFrame
    bki_subjects: pd.DataFrame
    bki_inquiries: pd.DataFrame
    bki_loans: pd.DataFrame
    truth: pd.DataFrame
    bankruptcy_cases: pd.DataFrame | None = None  # строятся после стоп-правил
    rfm_entries: pd.DataFrame | None = None


def months_before(dates: pd.DatetimeIndex, months) -> pd.DatetimeIndex:
    """Дата за заданное (дробное) число месяцев до dates."""
    days = np.round(np.asarray(months, dtype=float) * DAYS_PER_MONTH)
    return (dates - pd.to_timedelta(days, unit="D")).normalize()


def generate_population(ids: np.ndarray, app_dates: pd.DatetimeIndex, cfg: dict, scoring_cfg: dict,
                        rng: np.random.Generator, inns: InnFactory, loan_ids: IdCounter,
                        giant: np.ndarray) -> Population:
    """Компании на дату заявки. giant — строки-выбросы с выручкой, увеличенной в разы."""
    n = len(ids)
    pop = cfg["population"]
    ip = rng.random(n) < pop["ip_share"]
    young = rng.random(n) < pop["young_share"]
    mature = np.exp(rng.normal(np.log(pop["age_median_months"]), pop["age_sigma"], n))
    age = np.where(young, rng.uniform(1, 12, n), np.clip(mature, 12, 360))

    group = choose(rng, pop["okved_mix"], n)
    code = _okved_codes(rng, cfg["okved_codes"], group)

    # Скрытые качества бизнеса: от них зависят наблюдаемые признаки и риск.
    quality = rng.normal(size=n)
    stress = -0.6 * quality + 0.8 * rng.normal(size=n)

    revenue = (np.where(ip, pop["revenue_median"]["ip"], pop["revenue_median"]["ooo"])
               * (0.3 + 0.7 * np.minimum(age, 24) / 24)
               * np.exp(rng.normal(0, pop["revenue_sigma"], n) + 0.2 * quality))
    revenue = np.where(giant, revenue * cfg["anomalies"]["giant_multiplier"], revenue)
    revenue = np.clip(revenue, pop["revenue_min"], pop["revenue_cap"])

    flows = cfg["flows"]
    margins = {name: group_cfg["margin"] for name, group_cfg in scoring_cfg["okved_groups"].items()}
    margin = np.clip(pd.Series(group).map(margins).to_numpy() + flows["margin_bonus"]
                     + np.where(ip, flows["ip_margin_bonus"], 0.0)
                     + rng.normal(0, flows["margin_sd"], n) + 0.02 * quality, -0.10, 0.50)
    volatility = np.clip(rng.uniform(*flows["volatility"], n) * np.exp(-0.2 * quality), 0.02, 0.6)
    growth = np.clip(rng.normal(flows["growth_mean"] + 0.05 * quality, flows["growth_sd"]), -0.6, 1.0)
    marketplace = (group == "trade") & (rng.random(n) < pop["marketplace_share_of_trade"])
    top_share = np.where(marketplace, rng.uniform(*flows["marketplace_top_share"], n),
                         rng.beta(*flows["top_customer_beta"], n))

    ip_names = person_names(rng, int(ip.sum()))
    inn = np.empty(n, dtype=object)
    inn[ip] = inns.persons(int(ip.sum()))
    inn[~ip] = inns.companies(int((~ip).sum()))
    name = np.empty(n, dtype=object)
    name[ip] = [f"ИП {person}" for person in ip_names]
    name[~ip] = company_names(rng, int((~ip).sum()))
    registration = months_before(app_dates, age)

    companies = pd.DataFrame({
        "application_id": ids,
        "inn": inn.astype(str),
        "ogrn": inns.ogrn(inn, registration.year.to_numpy(), ip).astype(str),
        "legal_form": np.where(ip, "ip", "ooo"),
        "name": name.astype(str),
        "registration_date": registration,
        "status": "active",
        "bankruptcy_procedure": False,
        "in_rfm_list": False,
        "okved_code": code,
        "is_alfa_client": rng.random(n) < pop["alfa_client_share"],
        "fns_revenue": np.where(~ip & (age >= pop["fns_min_age_months"]),
                                np.round(revenue * np.exp(rng.normal(0, 0.1, n)), -3), np.nan),
        "ens_debt": _ens_debt(rng, cfg["tax"], stress),
    })
    persons, person_app, history = _persons(ids, ip, inn, ip_names, quality, app_dates, cfg, scoring_cfg, rng, inns)
    subjects, inquiries, loans = _credit_history(ids, app_dates, ip, young, inn, persons, person_app, quality, stress,
                                                 revenue, cfg, rng, loan_ids)
    truth = pd.DataFrame({
        "application_id": ids,
        "age_months": age,
        "okved_group": group,
        "quality": quality,
        "stress": stress,
        "true_revenue": revenue,
        "margin": margin,
        "volatility": volatility,
        "growth": growth,
        "top_customer_share": top_share,
        "is_marketplace": marketplace,
        "latent": rng.normal(size=n),
    })
    return Population(companies, persons, history, subjects, inquiries, loans, truth)


def registry_events(pop: Population, app_dates: pd.DatetimeIndex, rng: np.random.Generator) -> None:
    """Дела о банкротстве (ЕФРСБ) и записи перечня Росфинмониторинга по итоговым данным реестров."""
    comp, persons = pop.companies, pop.persons
    app_date = pd.Series(app_dates, index=comp["application_id"])

    def dates_of(app_ids) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(app_date.loc[app_ids].to_numpy())

    company = comp[comp["bankruptcy_procedure"]]
    person = persons[persons["bankruptcy_end_date"].notna()]
    person_end = pd.DatetimeIndex(person["bankruptcy_end_date"])
    pop.bankruptcy_cases = pd.concat([
        pd.DataFrame({
            "application_id": company["application_id"].to_numpy(),
            "debtor_inn": company["inn"].to_numpy(),
            "debtor_type": "company",
            "status": "in_progress",
            "start_date": months_before(dates_of(company["application_id"]), rng.uniform(1, 12, len(company))),
            "end_date": pd.NaT,
        }),
        pd.DataFrame({
            "application_id": person["application_id"].to_numpy(),
            "debtor_inn": person["inn"].to_numpy(),
            "debtor_type": "person",
            "status": "completed",
            "start_date": months_before(person_end, rng.uniform(6, 18, len(person))),
            "end_date": person_end,
        }),
    ], ignore_index=True)

    listed_companies = comp[comp["in_rfm_list"]]
    listed_persons = persons[persons["in_rfm_list"]]
    entries = pd.DataFrame({
        "application_id": np.concatenate([listed_companies["application_id"], listed_persons["application_id"]]),
        "inn": np.concatenate([listed_companies["inn"], listed_persons["inn"]]),
        "entity_type": ["company"] * len(listed_companies) + ["person"] * len(listed_persons),
    })
    entries["added_date"] = months_before(dates_of(entries["application_id"]), rng.uniform(1, 36, len(entries)))
    pop.rfm_entries = entries


def choose(rng, mapping: dict, n: int) -> np.ndarray:
    """n значений из ключей mapping с вероятностями из его значений."""
    values = np.array(list(mapping))
    probs = np.array(list(mapping.values()), dtype=float)
    return rng.choice(values, size=n, p=probs / probs.sum())


def _okved_codes(rng, codes_cfg: dict, group: np.ndarray) -> np.ndarray:
    codes = np.empty(group.size, dtype=object)
    for name in np.unique(group):
        mask = group == name
        codes[mask] = rng.choice(codes_cfg[name], size=int(mask.sum()))
    return codes.astype(str)


def _ens_debt(rng, tax: dict, stress: np.ndarray) -> np.ndarray:
    """Долг на ЕНС: настоящий растёт со стрессом, технический — мелкий, ниже порога фичи."""
    n = stress.size
    base_logit = np.log(tax["debt_prob"] / (1 - tax["debt_prob"]))
    debt = rng.random(n) < 1 / (1 + np.exp(-(base_logit + 0.8 * stress)))
    technical = ~debt & (rng.random(n) < tax["technical_debt_prob"])
    amount = np.where(debt, tax["debt_median"] * np.exp(rng.normal(0, 1, n)),
                      np.where(technical, rng.uniform(100, 9000, n), 0.0))
    return np.round(amount, 2)


def _persons(ids, ip, inn, ip_names, quality, app_dates, cfg, scoring_cfg, rng, inns):
    """ИП — сам предприниматель; у ООО — участники с долями и директор."""
    pc = cfg["persons"]
    n = len(ids)
    ip_idx = np.flatnonzero(ip)
    ooo_idx = np.flatnonzero(~ip)

    count = rng.choice([1, 2, 3], size=ooo_idx.size, p=pc["participants_probs"])
    part_app = np.repeat(ooo_idx, count)
    weights = rng.gamma(1.0, size=part_app.size)
    part_share = weights / np.bincount(part_app, weights=weights, minlength=n)[part_app]
    # Директор — крупнейший участник либо отдельный человек без доли.
    order = np.lexsort((-part_share, part_app))
    first_in_app = np.r_[True, part_app[order][1:] != part_app[order][:-1]]
    largest = order[first_in_app]
    director_is_part = rng.random(ooo_idx.size) < pc["director_is_participant"]
    part_director = np.zeros(part_app.size, dtype=bool)
    part_director[largest[director_is_part]] = True
    extra_app = ooo_idx[~director_is_part]

    app_idx = np.concatenate([ip_idx, part_app, extra_app])
    m = app_idx.size
    others = part_app.size + extra_app.size
    person_inn = np.concatenate([inn[ip_idx], inns.persons(others)])
    names = np.concatenate([ip_names, person_names(rng, others)])

    # Опыт собственника: проблемный чаще у слабого бизнеса.
    signal = -0.5 * quality[app_idx] + np.sqrt(0.75) * rng.normal(size=m)
    problem = signal > NormalDist().inv_cdf(1 - pc["problem_track_share"])
    first = ~problem & (rng.random(m) < 0.5)
    track = np.where(problem, "problem", np.where(first, "first", "ok"))

    # Часть проблемного опыта — давнее банкротство за пределами окна стоп-правила.
    rules = scoring_cfg["stop_rules"]
    window = np.where(ip[app_idx], rules["ip_bankruptcy_months"], rules["director_bankruptcy_months"])
    old = problem & (rng.random(m) < pc["old_bankruptcy_share_of_problem"])
    ended = months_before(app_dates[app_idx], window + rng.integers(1, 61, size=m))

    persons = pd.DataFrame({
        "application_id": ids[app_idx],
        "inn": person_inn.astype(str),
        "name": names.astype(str),
        "is_director": np.concatenate([np.ones(ip_idx.size, bool), part_director, np.ones(extra_app.size, bool)]),
        "share": np.concatenate([np.ones(ip_idx.size), part_share, np.zeros(extra_app.size)]),
        "track_record": track,
        "bankruptcy_end_date": pd.Series(ended).where(old).to_numpy(),
        "in_rfm_list": False,
    })
    history = _person_history(ids[app_idx], person_inn, names, track, old, app_dates[app_idx], rng, inns)
    return persons, app_idx, history


def _person_history(app_ids, person_inn, names, track, old_bankruptcy, app_dates, rng, inns) -> pd.DataFrame:
    """Другие бизнесы человека в ЕГРЮЛ/ЕГРИП — прошлые и действующие. Из них выводится опыт собственника.

    first — записей нет; ok — бизнесы работают или закрыты добровольно; problem — хотя бы один
    закрыт плохо, если проблема не в давнем личном банкротстве (оно видно в ЕФРСБ).
    """
    count = np.where(track == "first", 0, rng.integers(1, 3, track.size))
    owner = np.repeat(np.arange(track.size), count)
    k = owner.size
    first_row = np.r_[True, owner[1:] != owner[:-1]] if k else np.empty(0, dtype=bool)
    bad = (track[owner] == "problem") & ~old_bankruptcy[owner] & first_row
    role = rng.choice(["director", "participant", "ip"], size=k, p=[0.4, 0.3, 0.3])
    active = ~bad & (role != "ip") & (rng.random(k) < 0.4)
    outcome = np.where(bad, rng.choice(BAD_OUTCOMES, size=k), np.where(active, "active", "closed_voluntarily"))

    start = months_before(app_dates[owner], rng.uniform(24, 120, k))
    duration = pd.to_timedelta(np.round(rng.uniform(6, 60, k) * DAYS_PER_MONTH), unit="D")
    end = np.minimum((start + duration).to_numpy(), months_before(app_dates[owner], 1).to_numpy())
    # Прошлое ИП — та же персона со своим ИНН; компании — новые ИНН.
    org_inn = np.where(role == "ip", person_inn[owner], inns.companies(k))
    org_name = np.where(role == "ip", np.array([f"ИП {n}" for n in names[owner]], dtype=object),
                        company_names(rng, k))
    return pd.DataFrame({
        "application_id": app_ids[owner],
        "person_inn": person_inn[owner].astype(str),
        "org_inn": org_inn.astype(str),
        "org_name": org_name.astype(str),
        "role": role,
        "start_date": start,
        "end_date": pd.Series(end).where(outcome != "active").to_numpy(),
        "outcome": outcome,
    })


def _credit_history(ids, app_dates, ip, young, inn, persons, person_app, quality, stress, revenue, cfg, rng, loan_ids):
    """Субъекты БКИ (заёмщик и собственники ООО), запросы их историй и действующие кредиты заёмщика."""
    b = cfg["bki"]
    n = len(ids)
    ooo_person = ~ip[person_app]
    subj_app = np.concatenate([np.arange(n), person_app[ooo_person]])
    subj_inn = np.concatenate([inn, persons["inn"].to_numpy(dtype=object)[ooo_person]])
    borrower = np.concatenate([np.ones(n, bool), np.zeros(int(ooo_person.sum()), bool)])
    company = borrower & ~ip[subj_app]
    history_prob = np.where(company,
                            np.where(young[subj_app], b["company_history_prob"]["young"],
                                     b["company_history_prob"]["mature"]),
                            cfg["persons"]["history_prob"])
    has_history = rng.random(subj_app.size) < history_prob

    # Бизнес-кредиты заёмщика: долговая нагрузка растёт со стрессом.
    has_loans = rng.random(n) < b["business_loans_prob"] * np.where(young, b["young_loans_factor"], 1.0)
    ratio = np.exp(rng.normal(np.log(b["debt_to_revenue_median"]), b["debt_to_revenue_sigma"], n) + 0.3 * stress)
    count = 1 + np.minimum(rng.poisson(b["extra_loans_lambda"], n), 3)
    biz_app = np.repeat(np.flatnonzero(has_loans), count[has_loans])
    weights = rng.gamma(1.0, size=biz_app.size)
    biz_balance = ratio[biz_app] * revenue[biz_app] * weights / np.bincount(biz_app, weights=weights, minlength=n)[biz_app]
    lo, hi = b["remaining_months"]
    biz_left = rng.integers(lo, hi + 1, biz_app.size)
    biz_payment = annuity_payment(biz_balance, b["business_loan_rate"], biz_left)

    # Личные кредиты ИП: у ИП одна кредитная история и один кошелёк.
    consumer_app = np.flatnonzero(ip & (rng.random(n) < b["ip_consumer_loan_prob"]))
    consumer_balance = rng.uniform(1e5, 1.5e6, consumer_app.size)
    consumer_left = rng.integers(12, 61, consumer_app.size)
    mortgage_app = np.flatnonzero(ip & (rng.random(n) < b["ip_mortgage_prob"]))
    mortgage_balance = rng.uniform(2e6, 8e6, mortgage_app.size)
    mortgage_left = rng.integers(120, 241, mortgage_app.size)

    loan_app = np.concatenate([biz_app, consumer_app, mortgage_app])
    loans = pd.DataFrame({
        "application_id": ids[loan_app],
        "loan_id": loan_ids.take(loan_app.size),
        "subject_inn": inn[loan_app].astype(str),
        "lender": rng.choice(b["lenders"], size=loan_app.size),
        "is_business": np.concatenate([np.ones(biz_app.size, bool), np.zeros(consumer_app.size + mortgage_app.size, bool)]),
        "balance": np.round(np.concatenate([biz_balance, consumer_balance, mortgage_balance]), 2),
        "monthly_payment": np.round(np.concatenate([
            biz_payment,
            annuity_payment(consumer_balance, 0.25, consumer_left),
            annuity_payment(mortgage_balance, 0.10, mortgage_left),
        ]), 2),
        "remaining_months": np.concatenate([biz_left, consumer_left, mortgage_left]),
    })
    with_loans = np.zeros(n, dtype=bool)
    with_loans[loan_app] = True
    has_history |= borrower & with_loans[subj_app]

    # Просрочка: интервалы по долям из конфига, хуже у слабого бизнеса.
    cuts = [NormalDist().inv_cdf(c) for c in np.cumsum(list(b["dpd_shares"].values()))[:-1]]
    m = subj_app.size
    band = np.searchsorted(cuts, -0.7 * quality[subj_app] + 0.714 * rng.normal(size=m))
    days = np.select([band == 0, band == 1, band == 2],
                     [0, rng.integers(1, 30, m), rng.integers(30, 90, m)], rng.integers(90, 366, m))
    recent = rng.poisson(b["inquiries_base"] * np.exp(b["inquiries_stress"] * stress[subj_app]))
    subjects = pd.DataFrame({
        "application_id": ids[subj_app],
        "subject_inn": subj_inn.astype(str),
        "subject_type": np.where(company, "company", "person"),
        "is_borrower": borrower,
        "has_history": has_history,
        "max_dpd_24m": np.where(has_history, days, np.nan),
        "inquiries_90d": recent,
    })

    # Каждый запрос с датой: свежие — за последние 89 дней, старые (91–365 дней) в фичу не входят.
    old = rng.poisson(b["old_inquiries_lambda"], m)
    owner = np.concatenate([np.repeat(np.arange(m), recent), np.repeat(np.arange(m), old)])
    days_ago = np.concatenate([rng.integers(1, 90, int(recent.sum())), rng.integers(91, 366, int(old.sum()))])
    inquiries = pd.DataFrame({
        "application_id": ids[subj_app[owner]],
        "subject_inn": subj_inn[owner].astype(str),
        "inquiry_date": app_dates[subj_app[owner]] - pd.to_timedelta(days_ago, unit="D"),
        "lender": rng.choice(b["lenders"], size=owner.size),
    })
    return subjects, inquiries, loans
