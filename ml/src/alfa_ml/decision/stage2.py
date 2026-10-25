"""Решение этапа 2 — по выпискам: стоп-правила, PD модели 2, подбор суммы, срока и ставки.

Логика (config/scoring.yaml):
- сработало стоп-правило → REJECTED;
- полных месяцев выписок меньше stage2.min_statement_months → REJECTED: подать заявку позже;
- сетка «сумма × срок», как на этапе 1. PD₂ зависит от DSCR, DSCR — от платежа, платёж — от ставки,
  поэтому ставка клетки подбирается снизу вверх: первая корзина, в интервал которой попал PD₂
  при её ставке. Клетка проходит, если PD₂ ≤ stage2.cutoff_pd и DSCR по консервативному потоку ≥ min_dscr;
- проходит запрошенная клетка → APPROVED, любая другая → OFFER, никакая → REJECTED.
"""
import numpy as np
import pandas as pd

from alfa_ml.decision import heuristic, stop_rules
from alfa_ml.decision.stage1 import (Application, Decision, Option, application_data, flat_seasonality,
                                     max_by_term_options, percent, pick_offers, product, rate_buckets, rub)
from alfa_ml.features.build import model2_features, profile, repeat_profile
from alfa_ml.finance import annuity_payment
from alfa_ml.sources.read import SourceData


def decide_stage2(src: SourceData, statements: pd.DataFrame, app: Application, as_of, scoring_cfg: dict,
                  rules_cfg: dict, seasonality: pd.DataFrame, predict_pd=heuristic.predict_pd2,
                  model_version: str = heuristic.MODEL2_VERSION) -> Decision:
    """statements — помесячные обороты по всем предоставленным счетам (колонки alfa_turnover)."""
    hits = stop_rules.check_stop_rules(src.companies, src.persons, as_of, rules_cfg, scoring_cfg["stop_rules"])
    if hits:
        return Decision("REJECTED", 2, None, model_version, client_message=stop_rules.client_message(hits),
                        reasons=[f"Стоп-правило: {h.internal_reason} ({h.legal_basis})" for h in hits],
                        stop_rules=[h.id for h in hits])

    stage2 = scoring_cfg["stage2"]
    # Выручка этапа 1 (Альфа → ФНС → анкета) нужна для сверки с выписками.
    revenue1 = profile(application_data(src, app, as_of), scoring_cfg, flat_seasonality(scoring_cfg))["revenue1"]
    data = application_data(src, app, as_of)
    data.monthly = statements.assign(application_id=int(src.companies["application_id"].iloc[0]))
    prof = profile(data, scoring_cfg, seasonality)
    prof["revenue1"] = revenue1.to_numpy()
    months = int(prof["statement_months"].iloc[0])
    if months < stage2["min_statement_months"]:
        return Decision("REJECTED", 2, None, model_version,
                        client_message=f"Чтобы оценить бизнес, нужны обороты хотя бы за {stage2['min_statement_months']} "
                                       "полных месяца. Подайте заявку снова, когда они накопятся.",
                        reasons=[f"Полных месяцев оборотов: {months} — меньше {stage2['min_statement_months']}"])

    terms = np.array(scoring_cfg["terms_months"])
    amounts = np.unique(np.r_[app.credit_sum, np.arange(scoring_cfg["min_amount"], app.credit_sum,
                                                        scoring_cfg["amount_step"])])[::-1].astype(float)
    amount, term = np.meshgrid(amounts, terms, indexing="ij")
    cells = repeat_profile(prof, amount.size)
    rate = np.full(amount.shape, np.nan)
    pd2 = np.full(amount.shape, np.nan)
    buckets = rate_buckets(scoring_cfg, app)
    for k, bucket in enumerate(buckets):
        pd_k = predict_pd(model2_features(cells, amount.ravel(), term.ravel(), bucket["rate"])).reshape(amount.shape)
        # Последняя корзина заканчивается отсечкой модели 2 (включительно), остальные — своей границей.
        inside = pd_k <= stage2["cutoff_pd"] if k == len(buckets) - 1 else pd_k < bucket["max_pd"]
        take = np.isnan(rate) & inside
        rate[take], pd2[take] = bucket["rate"], pd_k[take]
        last_pd = pd_k
    no_bucket = np.isnan(rate)
    pd2[no_bucket] = last_pd[no_bucket]  # PD выше отсечки даже при самой высокой ставке
    rate_for_payment = np.where(no_bucket, buckets[-1]["rate"], rate)
    payment = annuity_payment(amount, rate_for_payment, term)
    dscr = prof["flow2"].iloc[0] / (payment + prof["existing_payments"].iloc[0])
    passes = ~no_bucket & (dscr >= scoring_cfg["min_dscr"])

    def option(i: int, j: int) -> Option:
        return Option(int(amount[i, j]), int(term[i, j]), float(rate[i, j]), int(round(payment[i, j])))

    requested_term = int(np.flatnonzero(terms == app.term_months)[0])
    pd_requested = float(pd2[0, requested_term])
    reasons = [
        f"Выручка по выпискам: {rub(prof['revenue2'].iloc[0])} ₽ в год, полных месяцев: {months}",
        f"Консервативный поток: {rub(prof['flow2'].iloc[0])} ₽ в месяц",
        f"PD этапа 2 на запрошенных условиях: {pd_requested:.1%} (отсечка {stage2['cutoff_pd']:.0%})",
        f"DSCR на запрошенных условиях: {dscr[0, requested_term]:.2f} (нужно не меньше {scoring_cfg['min_dscr']})",
        f"Цель: {app.purpose}; продукт: {product(app)}",
    ]
    max_by_term = max_by_term_options(passes, terms, option)

    if passes[0, requested_term]:
        approved = option(0, requested_term)
        return Decision("APPROVED", 2, pd_requested, model_version, approved=approved, max_by_term=max_by_term,
                        client_message=f"Кредит одобрен: {rub(approved.credit_sum)} ₽ на {approved.term_months} мес. "
                                       f"под {percent(approved.rate)} годовых, платёж {rub(approved.monthly_payment)} ₽ в месяц.",
                        reasons=reasons + ["Запрошенные условия проходят по PD и DSCR"])
    if passes.any():
        return Decision("OFFER", 2, pd_requested, model_version, max_by_term=max_by_term,
                        offers=pick_offers(passes, max_by_term, requested_term, option),
                        client_message="Запрошенную сумму на этих условиях одобрить не можем. "
                                       "Выберите один из предложенных вариантов.",
                        reasons=reasons + ["Запрошенные условия не проходят; подобраны варианты по выпискам"])
    return Decision("REJECTED", 2, pd_requested, model_version,
                    client_message="К сожалению, сейчас мы не можем предоставить кредит.",
                    reasons=reasons + ["По выпискам ни один вариант не проходит"])
