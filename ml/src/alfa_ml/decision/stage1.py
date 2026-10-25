"""Решение этапа 1 — без выписок: стоп-правила, PD модели 1, подбор суммы и срока.

Логика (config/scoring.yaml):
- сработало стоп-правило → REJECTED;
- PD₁ на запрошенной сумме выше stage1.decline_pd → REJECTED;
- иначе сетка «сумма × срок»: суммы от запрошенной вниз с шагом amount_step до min_amount,
  все сроки из terms_months. Клетка проходит, если PD₁ < stage1.approve_pd и DSCR по оценке
  потока ≥ min_dscr. Ставка клетки — корзина её PD;
- проходит запрошенная клетка → APPROVED; проходит любая другая → OFFER (для серой зоны —
  если включён stage1.grey_zone_offer); не проходит ничего → INFO: нужны выписки.
"""
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import pandas as pd

from alfa_ml.decision import heuristic, stop_rules
from alfa_ml.features.build import model1_features, profile, repeat_profile, stage1_dscr
from alfa_ml.finance import annuity_payment, rate_for_pd
from alfa_ml.sources.read import SourceData

SOURCE_NAMES = {"alfa_full": "обороты в Альфе за 12 мес.", "alfa_partial": "обороты в Альфе меньше 12 мес.",
                "fns": "данные ФНС за прошлый год", "declared": "анкета"}


@dataclass(frozen=True)
class Application:
    credit_sum: int
    term_months: int
    purpose: str
    refinance_loan_ids: tuple[int, ...] = ()
    revenue_last12m: float | None = None


@dataclass(frozen=True)
class Option:
    credit_sum: int
    term_months: int
    rate: float  # годовая, доля: 0.18
    monthly_payment: int


@dataclass
class Decision:
    decision: str  # APPROVED | OFFER | INFO | REJECTED
    stage: int
    pd: float | None
    model_version: str
    approved: Option | None = None
    offers: list[Option] = field(default_factory=list)
    max_by_term: list[tuple[int, Option | None]] = field(default_factory=list)
    documents_required: list[str] | None = None
    client_message: str = ""
    reasons: list[str] = field(default_factory=list)
    stop_rules: list[str] = field(default_factory=list)


class RevenueRequired(ValueError):
    """Выручки нет ни в источниках, ни в заявке — её нужно спросить у клиента."""


def _rub(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def application_data(src: SourceData, app: Application, as_of) -> SimpleNamespace:
    """Таблицы заявки в том виде, в каком их ждёт build.profile."""
    application_id = int(src.companies["application_id"].iloc[0])
    applications = pd.DataFrame({
        "application_id": [application_id],
        "application_date": [pd.Timestamp(as_of)],
        "requested_amount": [float(app.credit_sum)],
        "term_months": [app.term_months],
        "declared_revenue": [np.nan if app.revenue_last12m is None else float(app.revenue_last12m)],
        "refinance_loan_ids": [list(app.refinance_loan_ids)],
    })
    return SimpleNamespace(applications=applications, companies=src.companies, persons=src.persons,
                           bki_subjects=src.bki_subjects, bki_loans=src.bki_loans, monthly=src.monthly)


def flat_seasonality(scoring_cfg: dict) -> pd.DataFrame:
    """Сезонность без поправок — для этапа 1 тренд оборотов не нужен."""
    return pd.DataFrame(1.0, index=list(scoring_cfg["okved_groups"]), columns=range(1, 13))


def decide_stage1(src: SourceData, app: Application, as_of, scoring_cfg: dict, rules_cfg: dict,
                  predict_pd=heuristic.predict_pd, model_version: str = heuristic.MODEL_VERSION) -> Decision:
    hits = stop_rules.check_stop_rules(src.companies, src.persons, as_of, rules_cfg, scoring_cfg["stop_rules"])
    if hits:
        return Decision("REJECTED", 1, None, model_version, client_message=stop_rules.client_message(hits),
                        reasons=[f"Стоп-правило: {h.internal_reason} ({h.legal_basis})" for h in hits],
                        stop_rules=[h.id for h in hits])

    prof = profile(application_data(src, app, as_of), scoring_cfg, flat_seasonality(scoring_cfg))
    if not prof["revenue1"].iloc[0] > 0:
        raise RevenueRequired("Выручки нет в источниках — нужна выручка за 12 месяцев из анкеты")

    stage1 = scoring_cfg["stage1"]
    terms = np.array(scoring_cfg["terms_months"])
    amounts = np.unique(np.r_[app.credit_sum, np.arange(scoring_cfg["min_amount"], app.credit_sum,
                                                        scoring_cfg["amount_step"])])[::-1].astype(float)
    # PD этапа 1 зависит только от суммы (через долю в выручке), не от срока и ставки.
    pd_by_amount = predict_pd(model1_features(repeat_profile(prof, len(amounts)), amounts))
    rate_by_amount = rate_for_pd(pd_by_amount, scoring_cfg["rate_buckets"])
    amount, term = np.meshgrid(amounts, terms, indexing="ij")
    rate = np.repeat(rate_by_amount[:, None], len(terms), axis=1)
    dscr = stage1_dscr(repeat_profile(prof, amount.size), amount.ravel(), term.ravel(), rate.ravel())
    dscr = dscr.to_numpy().reshape(amount.shape)
    payment = np.round(annuity_payment(amount, rate, term)).astype(int)
    passes = (pd_by_amount[:, None] < stage1["approve_pd"]) & (dscr >= scoring_cfg["min_dscr"])

    def option(i: int, j: int) -> Option:
        return Option(int(amount[i, j]), int(term[i, j]), float(rate[i, j]), int(payment[i, j]))

    requested_term = int(np.flatnonzero(terms == app.term_months)[0])
    pd_requested = float(pd_by_amount[0])
    org = src.companies.iloc[0]
    source = prof["revenue_source"].iloc[0]
    reasons = [
        f"Выручка этапа 1: {_rub(prof['revenue1'].iloc[0])} ₽ — {SOURCE_NAMES[source]}",
        f"PD этапа 1 на запрошенной сумме: {pd_requested:.1%}",
        f"DSCR по оценке потока на запрошенных условиях: {dscr[0, requested_term]:.2f} "
        f"(нужно не меньше {scoring_cfg['min_dscr']})",
    ]
    documents = ["alfaAccountConsent"] if bool(org["is_alfa_client"]) else ["bankStatements"]
    statements_hint = ("разрешите использовать обороты по вашему счёту" if bool(org["is_alfa_client"])
                       else "загрузите выписки по расчётным счетам за 12 месяцев")

    if pd_requested > stage1["decline_pd"]:
        return Decision("REJECTED", 1, pd_requested, model_version,
                        client_message="К сожалению, сейчас мы не можем предоставить кредит.",
                        reasons=reasons + [f"PD выше порога отказа {stage1['decline_pd']:.0%}"])

    max_by_term = []
    for j, months in enumerate(terms):
        rows = np.flatnonzero(passes[:, j])
        max_by_term.append((int(months), option(rows[0], j) if rows.size else None))

    if passes[0, requested_term]:
        approved = option(0, requested_term)
        return Decision("APPROVED", 1, pd_requested, model_version, approved=approved, max_by_term=max_by_term,
                        client_message=f"Кредит одобрен: {_rub(approved.credit_sum)} ₽ на {approved.term_months} мес. "
                                       f"под {approved.rate:.0%} годовых, платёж {_rub(approved.monthly_payment)} ₽ в месяц.",
                        reasons=reasons + ["Запрошенные условия проходят по PD и DSCR"])

    grey_zone = pd_requested >= stage1["approve_pd"]
    if passes.any() and (not grey_zone or stage1["grey_zone_offer"]):
        offers = _pick_offers(passes, max_by_term, requested_term, option)
        return Decision("OFFER", 1, pd_requested, model_version, offers=offers, max_by_term=max_by_term,
                        documents_required=documents,
                        client_message="Запрошенную сумму на этих условиях одобрить не можем. Выберите один из "
                                       f"вариантов или {statements_hint} — мы пересмотрим решение.",
                        reasons=reasons + ["Запрошенные условия не проходят; подобраны варианты без выписок"])

    return Decision("INFO", 1, pd_requested, model_version, documents_required=documents,
                    client_message=f"Чтобы принять решение, {statements_hint}.",
                    reasons=reasons + ["Без выписок ни один вариант не проходит — нужен этап 2"])


def _pick_offers(passes: np.ndarray, max_by_term: list, requested_term: int, option) -> list[Option]:
    """До двух вариантов: максимальная сумма на запрошенный срок; запрошенная сумма на самом коротком
    сроке, где она проходит, а если не проходит нигде — максимальная сумма на самом длинном сроке."""
    candidates = [max_by_term[requested_term][1]]
    longer = np.flatnonzero(passes[0])
    candidates.append(option(0, longer[0]) if longer.size else max_by_term[-1][1])
    offers = []
    for candidate in candidates:
        if candidate is not None and candidate not in offers:
            offers.append(candidate)
    return offers
