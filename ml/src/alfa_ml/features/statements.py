"""Помесячные обороты по выпискам: операционный поток и его сводка. Общий код для обучения и скоринга."""
import numpy as np
import pandas as pd

OPERATIONAL_INFLOWS = ["inflow_customers", "inflow_acquiring", "inflow_cash"]
# Платежи по долгам, которых нет в БКИ (возврат займа учредителю), остаются в расходах.
OPERATIONAL_OUTFLOWS = ["outflow_suppliers", "outflow_salary", "outflow_rent", "outflow_taxes", "outflow_other_debt"]
# В поток не входят: переводы между своими счетами, полученные кредиты и займы,
# платежи по кредитам из БКИ (они в знаменателе DSCR), выплаты собственнику.


def monthly_cash_flow(monthly: pd.DataFrame) -> pd.DataFrame:
    """Операционные поступления, списания и свободный поток по каждому месяцу."""
    flows = monthly[["application_id", "month"]].copy()
    flows["operational_in"] = monthly[OPERATIONAL_INFLOWS].sum(axis=1)
    flows["operational_out"] = monthly[OPERATIONAL_OUTFLOWS].sum(axis=1)
    flows["free_cash_flow"] = flows["operational_in"] - flows["operational_out"]
    return flows


def flow_summary(monthly: pd.DataFrame, percentile: float) -> pd.DataFrame:
    """Сводка по заявке: число месяцев, консервативный поток, средние поступления, разброс потока."""
    grouped = monthly_cash_flow(monthly).groupby("application_id")
    return pd.DataFrame({
        "months": grouped.size(),
        "conservative_flow": grouped["free_cash_flow"].quantile(percentile / 100),
        "mean_inflow": grouped["operational_in"].mean(),
        "fcf_std": grouped["free_cash_flow"].std(ddof=0),
        "total_inflow": grouped["operational_in"].sum(),
    })


def seasonal_index(monthly: pd.DataFrame, groups: pd.Series, all_groups: list[str], min_months: int = 12) -> pd.DataFrame:
    """Сезонный индекс поступлений: строки — группы ОКВЭД, колонки — месяцы 1…12, среднее по строке 1.

    Считается по портфелю: поступления месяца делятся на средние поступления той же компании.
    Берутся только компании с полным годом выписок, иначе раскрутка молодого бизнеса исказит индекс.
    groups — группа ОКВЭД по application_id.
    """
    flows = monthly_cash_flow(monthly)
    counts = flows.groupby("application_id").size()
    flows = flows[flows["application_id"].isin(counts[counts >= min_months].index)]
    mean_in = flows.groupby("application_id")["operational_in"].transform("mean")
    flows = flows.assign(relative=flows["operational_in"] / mean_in.where(mean_in > 0),
                         group=flows["application_id"].map(groups), calendar=flows["month"].dt.month)
    table = flows.groupby(["group", "calendar"])["relative"].mean().unstack("calendar")
    table = table.reindex(index=all_groups, columns=range(1, 13)).fillna(1.0)
    return table.div(table.mean(axis=1), axis=0)


def turnover_trend(monthly: pd.DataFrame, groups: pd.Series, seasonality: pd.DataFrame, min_months: int = 12) -> pd.Series:
    """Поступления за последние 3 месяца к среднему за предыдущие 9, после снятия сезонности.

    NaN, если выписок меньше min_months: у молодого бизнеса рост — это раскрутка, а не тренд.
    """
    flows = monthly_cash_flow(monthly)
    group = flows["application_id"].map(groups)
    factor = seasonality.stack().reindex(pd.MultiIndex.from_arrays([group, flows["month"].dt.month])).to_numpy()
    flows = flows.assign(adjusted=flows["operational_in"] / factor).sort_values(["application_id", "month"])
    recency = flows.groupby("application_id").cumcount(ascending=False)  # 0 — последний месяц
    last = flows[recency < 3].groupby("application_id")["adjusted"].mean()
    previous = flows[(recency >= 3) & (recency < 12)].groupby("application_id")["adjusted"].mean()
    counts = flows.groupby("application_id").size()
    trend = (last / previous.where(previous > 0)).where(counts >= min_months)
    return trend.replace([np.inf, -np.inf], np.nan)


def top_customer_share(monthly: pd.DataFrame) -> pd.Series:
    """Доля крупнейшего покупателя в операционных поступлениях за весь период выписок."""
    flows = monthly_cash_flow(monthly)
    total = flows.groupby("application_id")["operational_in"].sum()
    top = monthly.groupby("application_id")["top_customer_inflow"].sum()
    return (top / total.where(total > 0)).clip(upper=1.0)
