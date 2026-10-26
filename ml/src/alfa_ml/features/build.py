"""Фичи моделей 1 и 2. Общий код для обучения, скоринга и сетки подбора суммы.

Сначала по заявке строится профиль — всё, что не зависит от суммы, срока и ставки.
Затем из профиля и условий кредита собираются матрицы фич; для сетки строки профиля
просто повторяются по клеткам.

data — объект с таблицами applications, companies, persons, bki_subjects, bki_loans, monthly:
выборка генератора при обучении или данные из баз-моков при скоринге.
"""
import numpy as np
import pandas as pd

from alfa_ml.features import external, statements
from alfa_ml.finance import annuity_payment

MODEL1_FEATURES = [
    "legal_form", "business_age_months", "okved_group", "loan_to_revenue", "debt_to_revenue", "revenue_size",
    "revenue_source", "max_dpd_24m", "bki_inquiries_90d", "has_tax_debt", "owner_track_record",
    "purpose", "has_collateral",
]
MODEL2_FEATURES = [
    "legal_form", "business_age_months", "okved_group", "owner_track_record", "max_dpd_24m", "bki_inquiries_90d",
    "has_tax_debt", "loan_to_revenue", "debt_to_revenue", "revenue_size",
    "dscr", "fcf_volatility", "turnover_trend", "revenue_consistency", "top_customer_share",
    "purpose", "has_collateral",
]
CATEGORICAL = ["legal_form", "okved_group", "revenue_source", "owner_track_record", "purpose"]
DAYS_PER_MONTH = 30.4375


def okved_group(codes: pd.Series, groups_cfg: dict) -> pd.Series:
    """Группа по первым двум цифрам основного кода ОКВЭД; не попавшие в диапазоны — other."""
    two_digits = pd.to_numeric(codes.astype(str).str[:2], errors="coerce")
    result = pd.Series("other", index=codes.index, dtype=object)
    for name, group in groups_cfg.items():
        for lo, hi in group["codes"]:
            result[(two_digits >= lo) & (two_digits <= hi)] = name
    return result


def revenue_source(is_alfa_client, statement_months, fns_revenue, min_months: int) -> np.ndarray:
    """Откуда берётся выручка этапа 1: alfa_full, alfa_partial, fns или declared (анкета).

    Приоритет: обороты в Альфе (клиент и хотя бы min_months полных месяцев) → ФНС → анкета.
    """
    months = np.asarray(statement_months)
    from_alfa = np.asarray(is_alfa_client, dtype=bool) & (months >= min_months)
    return np.select([from_alfa & (months >= 12), from_alfa, pd.notna(np.asarray(fns_revenue, dtype=float))],
                     ["alfa_full", "alfa_partial", "fns"], "declared")


def profile(data, scoring_cfg: dict, seasonality: pd.DataFrame) -> pd.DataFrame:
    """Профиль заявки: статичные фичи и всё, из чего считаются фичи, зависящие от условий кредита.

    seasonality — сезонный индекс групп ОКВЭД, оценённый на обучающей выборке (statements.seasonal_index).
    """
    feat = scoring_cfg["features"]
    apps = data.applications.set_index("application_id")
    ids = apps.index
    comp = data.companies.set_index("application_id").reindex(ids)
    threshold = feat["owner_share_threshold"]
    groups_cfg = scoring_cfg["okved_groups"]

    group = okved_group(comp["okved_code"], groups_cfg)
    ip = comp["legal_form"] == "ip"
    living = ip.astype(float) * feat["ip_living_cost_monthly"]
    loans = external.kept_loans(data.bki_loans, data.applications)

    # Выписки: у клиентов Альфы есть уже на этапе 1, у остальных — только после загрузки.
    summary = statements.flow_summary(data.monthly, feat["conservative_flow_percentile"]).reindex(ids)
    months = summary["months"].fillna(0).astype(int)
    enough_for_revenue = months >= feat["revenue_min_months"]
    statement_revenue = (summary["total_inflow"] / months.where(months > 0) * 12).where(enough_for_revenue)

    # Выручка этапа 1 по приоритету: обороты в Альфе → ФНС (только ООО) → анкета.
    source = revenue_source(comp["is_alfa_client"], months, comp["fns_revenue"], feat["revenue_min_months"])
    from_alfa = pd.Series(np.isin(source, ["alfa_full", "alfa_partial"]), index=ids)
    revenue1 = statement_revenue.where(from_alfa, comp["fns_revenue"]).fillna(apps["declared_revenue"])

    margin = group.map({name: g["margin"] for name, g in groups_cfg.items()})
    groups_by_app = pd.Series(group.to_numpy(), index=ids)
    enough_for_model2 = months >= scoring_cfg["stage2"]["min_statement_months"]
    trend = statements.turnover_trend(data.monthly, groups_by_app, seasonality, feat["trend_min_months"])

    return pd.DataFrame({
        "legal_form": comp["legal_form"],
        "business_age_months": (apps["application_date"] - comp["registration_date"]).dt.days / DAYS_PER_MONTH,
        "okved_group": group,
        "revenue_source": source,
        "max_dpd_24m": external.max_dpd(data.bki_subjects, data.persons, ids, threshold),
        "bki_inquiries_90d": external.borrower_inquiries(data.bki_subjects, ids),
        "has_tax_debt": (comp["ens_debt"] > feat["tax_debt_threshold"]).astype(int),
        "owner_track_record": external.worst_track_record(data.persons, ids, threshold),
        "purpose": apps["purpose"],
        "has_collateral": apps["has_collateral"].astype(int),
        "revenue1": _positive(revenue1),
        "business_debt": external.business_debt(loans, ids),
        "existing_payments": external.existing_payments(loans, ids),
        # Поток этапа 1 — оценка по выручке и типовой марже группы с понижающим коэффициентом.
        "flow1": revenue1 / 12 * margin * scoring_cfg["stage1"]["flow_haircut"] - living,
        "statement_months": months,
        "revenue2": _positive(statement_revenue).where(enough_for_model2),
        # Поток этапа 2 — консервативный (20-й перцентиль месячного свободного потока) по выпискам.
        "flow2": (summary["conservative_flow"] - living).where(enough_for_model2),
        "fcf_volatility": (summary["fcf_std"] / summary["mean_inflow"].where(summary["mean_inflow"] > 0))
        .where(enough_for_model2),
        "turnover_trend": trend.reindex(ids),
        "top_customer_share": statements.top_customer_share(data.monthly).reindex(ids).where(enough_for_model2),
    }, index=ids)


def _positive(values: pd.Series) -> pd.Series:
    """Выручка, на которую можно делить: нулевая и отрицательная — пропуск."""
    return values.where(values > 0)


def model1_features(prof: pd.DataFrame, amount) -> pd.DataFrame:
    """13 фич модели 1. amount — запрошенная сумма по строкам профиля."""
    amount = np.asarray(amount, dtype=float)
    return pd.DataFrame({
        "legal_form": prof["legal_form"],
        "business_age_months": prof["business_age_months"],
        "okved_group": prof["okved_group"],
        "loan_to_revenue": amount / prof["revenue1"],
        "debt_to_revenue": prof["business_debt"] / prof["revenue1"],
        "revenue_size": prof["revenue1"],
        "revenue_source": prof["revenue_source"],
        "max_dpd_24m": prof["max_dpd_24m"],
        "bki_inquiries_90d": prof["bki_inquiries_90d"],
        "has_tax_debt": prof["has_tax_debt"],
        "owner_track_record": prof["owner_track_record"],
        "purpose": prof["purpose"],
        "has_collateral": prof["has_collateral"],
    }, index=prof.index)[MODEL1_FEATURES]


def model2_features(prof: pd.DataFrame, amount, term, rate) -> pd.DataFrame:
    """17 фич модели 2. Строки без достаточных выписок — пропуски в фичах из выписок."""
    amount = np.asarray(amount, dtype=float)
    payment = annuity_payment(amount, rate, term) + prof["existing_payments"].to_numpy()
    return pd.DataFrame({
        "legal_form": prof["legal_form"],
        "business_age_months": prof["business_age_months"],
        "okved_group": prof["okved_group"],
        "owner_track_record": prof["owner_track_record"],
        "max_dpd_24m": prof["max_dpd_24m"],
        "bki_inquiries_90d": prof["bki_inquiries_90d"],
        "has_tax_debt": prof["has_tax_debt"],
        "loan_to_revenue": amount / prof["revenue2"],
        "debt_to_revenue": prof["business_debt"] / prof["revenue2"],
        "revenue_size": prof["revenue2"],
        "dscr": prof["flow2"] / payment,
        "fcf_volatility": prof["fcf_volatility"],
        "turnover_trend": prof["turnover_trend"],
        "revenue_consistency": prof["revenue2"] / prof["revenue1"],
        "top_customer_share": prof["top_customer_share"],
        "purpose": prof["purpose"],
        "has_collateral": prof["has_collateral"],
    }, index=prof.index)[MODEL2_FEATURES]


def stage1_dscr(prof: pd.DataFrame, amount, term, rate) -> pd.Series:
    """DSCR по оценке потока этапа 1 — ограничение при подборе суммы, не фича модели."""
    payment = annuity_payment(np.asarray(amount, dtype=float), rate, term) + prof["existing_payments"].to_numpy()
    return prof["flow1"] / payment


def repeat_profile(prof: pd.DataFrame, times: int) -> pd.DataFrame:
    """Профиль, где каждая строка повторена times раз подряд — для клеток сетки подбора суммы."""
    return prof.loc[prof.index.repeat(times)]
