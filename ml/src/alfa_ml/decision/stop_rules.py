"""Стоп-правила: юридические запреты, при которых кредит не выдаётся без расчёта модели.

Тексты и правовые основания — в config/rules.yaml, окна запретов — в config/scoring.yaml.
"""
import datetime as dt
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RuleHit:
    id: str
    client_message: str
    internal_reason: str
    legal_basis: str


def full_months(start: dt.date, end: dt.date) -> int:
    """Полных календарных месяцев от start до end: с 15.01 до 14.02 — 0, до 15.02 — 1."""
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end.day < start.day)


def check_stop_rules(companies: pd.DataFrame, persons: pd.DataFrame, as_of, rules_cfg: dict,
                     windows: dict) -> list[RuleHit]:
    """Сработавшие стоп-правила по данным одной заявки (таблицы read_sources или генератора).

    windows — scoring.yaml/stop_rules: ip_bankruptcy_months и director_bankruptcy_months.
    """
    as_of = pd.Timestamp(as_of).date()
    rules = {rule["id"]: rule for rule in rules_cfg["rules"]}
    org = companies.iloc[0]
    hits = []

    def hit(rule_id: str, **details):
        rule = rules[rule_id]
        hits.append(RuleHit(rule_id, rule["client_message"], rule["internal_reason"].format(**details),
                            rule["legal_basis"]))

    if org["status"] != "active":
        hit("inactive_status", status=org["status"])
    if bool(org["bankruptcy_procedure"]):
        hit("company_bankruptcy")

    # Банкротство ИП (5 лет нельзя быть ИП) или директора ООО (3 года нельзя управлять юрлицом).
    window = windows["ip_bankruptcy_months"] if org["legal_form"] == "ip" else windows["director_bankruptcy_months"]
    for _, person in persons[persons["is_director"] & persons["bankruptcy_end_date"].notna()].iterrows():
        months = full_months(pd.Timestamp(person["bankruptcy_end_date"]).date(), as_of)
        if months < window:
            hit("owner_bankruptcy", inn=person["inn"], months=months, window=window)

    listed = [org["inn"]] if bool(org["in_rfm_list"]) else []
    listed += persons.loc[persons["in_rfm_list"].astype(bool), "inn"].tolist()
    if listed:
        hit("rfm_list", inn=", ".join(listed))
    return hits


def client_message(hits: list[RuleHit]) -> str:
    """Текст отказа для клиента. Если среди причин перечень Росфинмониторинга — только нейтральный текст."""
    for rule_hit in hits:
        if rule_hit.id == "rfm_list":
            return rule_hit.client_message
    return hits[0].client_message
