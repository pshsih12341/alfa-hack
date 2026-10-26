import datetime as dt

import numpy as np
import pandas as pd
import pytest

from alfa_ml.config import load_config
from alfa_ml.sources.schema import TURNOVER_COLUMNS
from alfa_ml.statements import onec
from alfa_ml.statements.categorize import categorize, client_share, combine, monthly_aggregates
from alfa_ml.synth.datasets import Context, Segment, build_sample
from alfa_ml.synth.ids import IdCounter, InnFactory
from alfa_ml.synth.onec_files import statement_file

AS_OF = "2026-11-01"
CLIENT = "7707083893"
ACCOUNT = "40702810100000000001"


def _doc(amount, payer_inn, payer_account, receiver_inn, receiver_account, purpose, kbk=""):
    inflow = receiver_account == ACCOUNT
    date = dt.date(2026, 5, 10)
    return {"number": "1", "date": date, "amount": amount, "payer_inn": payer_inn, "payer_name": "a",
            "payer_account": payer_account, "receiver_inn": receiver_inn, "receiver_name": "b",
            "receiver_account": receiver_account, "date_credited": date if inflow else None,
            "date_debited": None if inflow else date, "purpose": purpose, "kbk": kbk, "payment_kind": "01"}


@pytest.mark.parametrize(("doc", "category"), [
    (_doc(100, "5000000000", "40702810900000000099", CLIENT, ACCOUNT, "Оплата по счёту № 5"), "inflow_customers"),
    (_doc(100, "7728168971", "30101810000000000001", CLIENT, ACCOUNT, "Возмещение по операциям эквайринга"), "inflow_acquiring"),
    (_doc(100, "7728168971", "30101810000000000001", CLIENT, ACCOUNT, "Взнос наличных"), "inflow_cash"),
    (_doc(100, CLIENT, "40702810200000000002", CLIENT, ACCOUNT, "Перевод собственных средств"), "inflow_own_transfer"),
    (_doc(100, "7728168971", "30101810000000000001", CLIENT, ACCOUNT, "Предоставление кредита по договору"), "inflow_loans"),
    (_doc(100, "500100732259", "40817810000000000003", CLIENT, ACCOUNT, "Предоставление займа"), "inflow_owner_funding"),
    (_doc(100, CLIENT, ACCOUNT, "7727406020", "03100643000000018500", "Единый налоговый платёж", "18201061201010000510"), "outflow_taxes"),
    (_doc(100, CLIENT, ACCOUNT, "7728168971", "30101810000000000001", "Погашение кредита и процентов"), "outflow_loan_payments"),
    (_doc(100, CLIENT, ACCOUNT, "500100732259", "40817810000000000003", "Возврат займа по договору"), "outflow_other_debt"),
    (_doc(100, CLIENT, ACCOUNT, "500100732259", "40817810000000000003", "Выплата дивидендов участнику"), "outflow_owner_payouts"),
    (_doc(100, CLIENT, ACCOUNT, "7728168971", "30101810000000000001", "Перечисление заработной платы"), "outflow_salary"),
    (_doc(100, CLIENT, ACCOUNT, "5000000001", "40702810900000000098", "Арендная плата за май"), "outflow_rent"),
    (_doc(100, CLIENT, ACCOUNT, "5000000002", "40702810900000000097", "Оплата по договору поставки"), "outflow_suppliers"),
    (_doc(100, CLIENT, ACCOUNT, CLIENT, "40702810200000000002", "Перевод между своими счетами"), "outflow_own_transfer"),
    (_doc(100, CLIENT, ACCOUNT, CLIENT, "40817810000000000004", "Перевод на личный счёт"), "outflow_owner_payouts"),
])
def test_categorization_rules(doc, category):
    raw = onec.write(ACCOUNT, dt.date(2026, 5, 1), dt.date(2026, 5, 31), [doc], dt.date(2026, 6, 1))
    assert categorize(onec.parse(raw), CLIENT)["category"].tolist() == [category]


def test_parse_rejects_other_files_and_reads_both_encodings():
    with pytest.raises(onec.StatementFormatError):
        onec.parse("просто текст".encode("utf-8"))
    raw = onec.write(ACCOUNT, dt.date(2026, 5, 1), dt.date(2026, 5, 31),
                     [_doc(1234.5, "5000000000", "40702810900000000099", CLIENT, ACCOUNT, "Оплата № 1 «товар»")],
                     dt.date(2026, 6, 1))
    for encoded in (raw, raw.decode("cp1251").encode("utf-8")):
        statement = onec.parse(encoded)
        assert statement.account == ACCOUNT and statement.documents["amount"].tolist() == [1234.5]
        assert statement.documents["purpose"].iloc[0] == "Оплата № 1 «товар»"
    assert client_share(onec.parse(raw), CLIENT) == 1.0 and client_share(onec.parse(raw), "5000000001") == 0.0


@pytest.fixture(scope="module")
def batch():
    gen, scoring = load_config("generator"), load_config("scoring")
    ctx = Context(gen, scoring, InnFactory(np.random.default_rng(21)), IdCounter(), IdCounter())
    return build_sample([Segment(120, gen)], (AS_OF, AS_OF), ctx, np.random.SeedSequence(21))[0]


def test_round_trip_restores_monthly_sums(batch):
    """Суммы → файл 1С → разбор → разметка → суммы: совпадают до копейки."""
    persons = batch.persons[batch.persons["is_director"]].set_index("application_id")
    checked = 0
    for _, org in batch.companies.iterrows():
        original = batch.monthly[batch.monthly["application_id"] == org["application_id"]]
        if original.empty:
            continue
        owner = {"inn": persons.loc[org["application_id"], "inn"], "name": persons.loc[org["application_id"], "name"]}
        raw = statement_file(original, org["inn"], org["name"], org["legal_form"], owner, AS_OF)
        statement = onec.parse(raw)
        assert client_share(statement, org["inn"]) == 1.0
        restored = monthly_aggregates(categorize(statement, org["inn"]), org["application_id"], AS_OF)
        expected = original.sort_values("month").reset_index(drop=True)
        assert restored["month"].tolist() == expected["month"].tolist()
        money = [c for c in TURNOVER_COLUMNS if c != "top_customer_inflow"]
        assert np.allclose(restored[money].to_numpy(), expected[money].to_numpy(), atol=0.011), org["inn"]
        # Крупнейший покупатель восстанавливается, если остальных покупателей хватает, чтобы каждый был меньше.
        assert (restored["top_customer_inflow"] >= expected["top_customer_inflow"] - 0.011).all()
        checked += 1
        if checked == 40:
            break
    assert checked == 40


def test_combine_accounts():
    months = pd.to_datetime(["2026-08-01", "2026-09-01"])
    first = pd.DataFrame({"application_id": 1, "month": months, **{c: 100.0 for c in TURNOVER_COLUMNS}})
    second = pd.DataFrame({"application_id": 1, "month": months[1:], **{c: 50.0 for c in TURNOVER_COLUMNS}})
    combined = combine(first, second)
    assert combined["inflow_customers"].tolist() == [100.0, 150.0]
    assert combined["top_customer_inflow"].tolist() == [100.0, 100.0]  # крупнейший — максимум, а не сумма
