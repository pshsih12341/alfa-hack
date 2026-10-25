"""Разметка операций выписки по категориям и помесячные суммы — в тех же колонках, что обороты в Альфе.

Правила (порядок важен):
- свой ИНН с обеих сторон: у ИП счёт 40817 — личный счёт предпринимателя (вывод себе или пополнение
  со своей карты), иначе — перевод между своими счетами;
- налоги: получатель — казначейство (ФНС) или указан КБК;
- кредиты банка: «кредит» + «погашение/проценты» в списаниях, «кредит» + «выдача/предоставление» в поступлениях;
- займы вне БКИ: поступление — не выручка, возврат — остаётся в расходах;
- ключевые слова: эквайринг, наличные, зарплата, аренда, дивиденды;
- остальные поступления — от покупателей, остальные списания — поставщикам.
"""
import re

import pandas as pd

from alfa_ml.sources.schema import TURNOVER_COLUMNS
from alfa_ml.statements.onec import Statement

TREASURY_INN = "7727406020"  # Казначейство России (ФНС России) — получатель единого налогового платежа
PERSONAL_ACCOUNT = "40817"  # счёт физлица


def _category(inflow: bool, own: bool, personal: bool, tax: bool, text: str) -> str:
    if inflow:
        if own:
            return "inflow_owner_funding" if personal else "inflow_own_transfer"
        if "кредит" in text and re.search(r"выдач|предостав|зачислен", text):
            return "inflow_loans"
        if "займ" in text:
            return "inflow_owner_funding"
        if "эквайринг" in text:
            return "inflow_acquiring"
        if re.search(r"наличн|инкассац", text):
            return "inflow_cash"
        return "inflow_customers"
    if own:
        return "outflow_owner_payouts" if personal else "outflow_own_transfer"
    if tax:
        return "outflow_taxes"
    if "кредит" in text and re.search(r"погашени|процент", text):
        return "outflow_loan_payments"
    if "займ" in text:
        return "outflow_other_debt"
    if "дивиденд" in text:
        return "outflow_owner_payouts"
    if re.search(r"заработн|зарплат", text):
        return "outflow_salary"
    if "аренд" in text:
        return "outflow_rent"
    return "outflow_suppliers"


def categorize(statement: Statement, client_inn: str) -> pd.DataFrame:
    """Операции выписки: дата, сумма, категория, ИНН контрагента. Документы не по этому счёту отбрасываются."""
    docs = statement.documents
    inflow = docs["receiver_account"] == statement.account
    outflow = docs["payer_account"] == statement.account
    docs = docs[inflow | outflow]
    inflow = inflow[docs.index]
    other_inn = docs["payer_inn"].where(inflow, docs["receiver_inn"])
    other_account = docs["payer_account"].where(inflow, docs["receiver_account"])
    tax = (docs["receiver_inn"] == TREASURY_INN) | (docs["kbk"].str.len() > 0)
    categories = [
        _category(bool(i), o == client_inn, a.startswith(PERSONAL_ACCOUNT), bool(t), str(p).lower())
        for i, o, a, t, p in zip(inflow, other_inn, other_account, tax, docs["purpose"])
    ]
    dates = docs["date_credited"].where(inflow, docs["date_debited"]).fillna(docs["date"])
    return pd.DataFrame({"date": dates.to_numpy(), "amount": docs["amount"].to_numpy(),
                         "category": categories, "counterparty_inn": other_inn.to_numpy()})


def client_share(statement: Statement, client_inn: str) -> float:
    """Доля документов, где клиент — плательщик или получатель: проверка, что выписка его."""
    docs = statement.documents
    if docs.empty:
        return 0.0
    return float(((docs["payer_inn"] == client_inn) | (docs["receiver_inn"] == client_inn)).mean())


def monthly_aggregates(operations: pd.DataFrame, application_id: int, as_of, months: int = 12) -> pd.DataFrame:
    """Суммы по категориям за полные месяцы до даты заявки — в колонках alfa_turnover.

    top_customer_inflow — поступления от крупнейшего покупателя (по ИНН) в этом месяце.
    """
    month_start = pd.Timestamp(as_of).to_period("M").start_time
    ops = operations.assign(month=pd.to_datetime(operations["date"]).dt.to_period("M").dt.start_time)
    ops = ops[(ops["month"] >= month_start - pd.DateOffset(months=months)) & (ops["month"] < month_start)]
    sums = ops.pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0.0)
    customers = ops[ops["category"] == "inflow_customers"]
    top = customers.groupby(["month", "counterparty_inn"])["amount"].sum().groupby("month").max()
    sums["top_customer_inflow"] = top
    result = sums.reindex(columns=TURNOVER_COLUMNS, fill_value=0.0).fillna(0.0).round(2).reset_index()
    result.insert(0, "application_id", application_id)
    return result.sort_values("month").reset_index(drop=True)


def combine(*monthly: pd.DataFrame) -> pd.DataFrame:
    """Обороты по нескольким счетам — сумма по месяцам; крупнейший покупатель — максимум по счетам."""
    frames = [m for m in monthly if m is not None and len(m)]
    if not frames:
        return monthly[0]
    joined = pd.concat(frames, ignore_index=True)
    money = [c for c in TURNOVER_COLUMNS if c != "top_customer_inflow"]
    grouped = joined.groupby(["application_id", "month"], as_index=False)
    result = grouped[money].sum().merge(grouped["top_customer_inflow"].max(), on=["application_id", "month"])
    return result[["application_id", "month", *TURNOVER_COLUMNS]].sort_values("month").reset_index(drop=True)
