"""Выписки в формате 1С из помесячных сумм генератора — для демо-файлов и проверки разбора.

Каждая категория месяца раскладывается на несколько платёжек с правдоподобными контрагентами и
назначениями; крупнейший покупатель получает ровно свою сумму. Разбор такого файла
(statements.onec + statements.categorize) восстанавливает исходные суммы до копейки.

Запуск из ml/: uv run python -m alfa_ml.synth.onec_files --inn 5991587272 --out ../mocks/statements
"""
import argparse
import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

from alfa_ml.sources.schema import TURNOVER_COLUMNS
from alfa_ml.statements import onec
from alfa_ml.statements.categorize import TREASURY_INN
from alfa_ml.synth.ids import InnFactory, company_names, person_names

BANK = {"inn": "7728168971", "name": "АО «Банк Партнёр»"}
TAX = {"inn": TREASURY_INN, "name": "Казначейство России (ФНС России)", "account": "03100643000000018500"}
KBK = "18201061201010000510"
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
          "ноябрь", "декабрь"]


class _Builder:
    def __init__(self, inn: str, name: str, legal_form: str, owner: dict, seed: int):
        self.rng = np.random.default_rng(seed)
        prefix = "40802810" if legal_form == "ip" else "40702810"
        self.ip = legal_form == "ip"
        self.client = {"inn": inn, "name": name, "account": self._account(prefix)}
        self.other_own = {**self.client, "account": self._account(prefix)}  # свой счёт в другом банке
        self.personal = {**self.client, "account": self._account("40817810")}  # личный счёт ИП
        self.owner = {**owner, "account": self._account("40817810")}
        self.bank = {**BANK, "account": self._account("30101810")}
        factory = InnFactory(self.rng)
        names = company_names(self.rng, 31)
        inns = factory.companies(31)
        parties = [{"inn": i, "name": n, "account": self._account("40702810")} for i, n in zip(inns, names)]
        self.buyers, self.suppliers, self.landlord = parties[:25], parties[25:30], parties[30]
        # Займ вне БКИ: у ООО — от учредителя, у ИП — от частного лица (сам себе ИП не занимает).
        lender_inn = factory.persons(1)[0]
        self.lender = {"inn": lender_inn, "name": person_names(self.rng, 1)[0],
                       "account": self._account("40817810")} if self.ip else self.owner
        self.documents = []

    def _account(self, prefix: str) -> str:
        return prefix + "".join(str(d) for d in self.rng.integers(0, 10, 12))

    @staticmethod
    def _equal(amount: float, parts: int) -> list[float]:
        """Сумма на parts почти равных частей до копейки."""
        cents = round(amount * 100)
        pieces = np.full(parts, cents // parts)
        pieces[: cents - pieces.sum()] += 1
        return [p / 100 for p in pieces if p > 0]

    def _split(self, amount: float, parts: int) -> list[float]:
        """Сумма на parts положительных частей до копейки."""
        cents = round(amount * 100)
        parts = max(1, min(parts, cents))
        weights = self.rng.dirichlet(np.ones(parts) * 3)
        pieces = np.floor(weights * cents).astype(int)
        pieces[-1] += cents - pieces.sum()
        return [p / 100 for p in pieces if p > 0]

    def _day(self, month: pd.Timestamp) -> dt.date:
        return (month + pd.Timedelta(days=int(self.rng.integers(0, 27)))).date()

    def pay(self, month, amount: float, payer: dict, receiver: dict, purpose: str, kbk: str = "") -> None:
        date = self._day(month)
        inflow = receiver["account"] == self.client["account"]
        self.documents.append({
            "number": str(len(self.documents) + 1), "date": date, "amount": amount,
            "payer_account": payer["account"], "payer_inn": payer["inn"], "payer_name": payer["name"],
            "receiver_account": receiver["account"], "receiver_inn": receiver["inn"], "receiver_name": receiver["name"],
            "date_credited": date if inflow else None, "date_debited": None if inflow else date,
            "purpose": purpose, "kbk": kbk, "payment_kind": "01",
        })

    def month(self, row: pd.Series) -> None:
        m, c = row["month"], self.client
        number = lambda: int(self.rng.integers(10, 999))  # noqa: E731

        customers, top = row["inflow_customers"], min(row["top_customer_inflow"], row["inflow_customers"])
        rest = round(customers - top, 2)
        for amount in self._split(top, int(self.rng.integers(1, 3))) if top > 0 else []:
            self.pay(m, amount, self.buyers[0], c, f"Оплата по счёту № {number()} за товары и услуги")
        if rest > 0:
            # Остальные покупатели — поровну и каждый меньше крупнейшего (если покупателей хватает).
            others = 3 if top <= 0 else min(len(self.buyers) - 1, max(1, math.ceil(rest / (0.8 * top))))
            for buyer, amount in zip(self.buyers[1:], self._equal(rest, others)):
                self.pay(m, amount, buyer, c, f"Оплата по счёту № {number()} за товары и услуги")

        for amount in self._split(row["inflow_acquiring"], 4) if row["inflow_acquiring"] > 0 else []:
            self.pay(m, amount, self.bank, c, "Возмещение по операциям эквайринга за период")
        for amount in self._split(row["inflow_cash"], 2) if row["inflow_cash"] > 0 else []:
            self.pay(m, amount, self.bank, c, "Взнос наличных денежных средств на счёт")
        if row["inflow_own_transfer"] > 0:
            self.pay(m, row["inflow_own_transfer"], self.other_own, c, "Перевод собственных средств между счетами")
        if row["inflow_loans"] > 0:
            self.pay(m, row["inflow_loans"], self.bank, c, f"Предоставление кредита по кредитному договору № {number()}")
        if row["inflow_owner_funding"] > 0:
            if self.ip:
                self.pay(m, row["inflow_owner_funding"], self.personal, c, "Пополнение счёта собственными средствами")
            else:
                self.pay(m, row["inflow_owner_funding"], self.owner, c, f"Предоставление займа по договору займа № {number()}")

        for supplier, amount in zip(self.suppliers, self._split(row["outflow_suppliers"], 4)) if row["outflow_suppliers"] > 0 else []:
            self.pay(m, amount, c, supplier, f"Оплата по договору поставки № {number()} за товар")
        for amount in self._split(row["outflow_salary"], 2) if row["outflow_salary"] > 0 else []:
            self.pay(m, amount, c, self.bank, f"Перечисление заработной платы по реестру № {number()}")
        if row["outflow_rent"] > 0:
            self.pay(m, row["outflow_rent"], c, self.landlord, f"Арендная плата за {MONTHS[m.month - 1]}")
        for amount in self._split(row["outflow_taxes"], 2) if row["outflow_taxes"] > 0 else []:
            self.pay(m, amount, c, TAX, "Единый налоговый платёж", kbk=KBK)
        if row["outflow_other_debt"] > 0:
            self.pay(m, row["outflow_other_debt"], c, self.lender, f"Возврат займа по договору займа № {number()}")
        if row["outflow_own_transfer"] > 0:
            self.pay(m, row["outflow_own_transfer"], c, self.other_own, "Перевод собственных средств между счетами")
        if row["outflow_loan_payments"] > 0:
            self.pay(m, row["outflow_loan_payments"], c, self.bank,
                     f"Погашение кредита и процентов по кредитному договору № {number()}")
        if row["outflow_owner_payouts"] > 0:
            if self.ip:
                self.pay(m, row["outflow_owner_payouts"], c, self.personal, "Перевод собственных средств на личный счёт")
            else:
                self.pay(m, row["outflow_owner_payouts"], c, self.owner, "Выплата дивидендов участнику")


def statement_file(monthly: pd.DataFrame, inn: str, name: str, legal_form: str, owner: dict, as_of) -> bytes:
    """Файл 1С для одной компании: monthly — её строки (колонки alfa_turnover), owner — {inn, name}."""
    builder = _Builder(inn, name, legal_form, owner, seed=int(inn) % 2**32)
    rows = monthly.sort_values("month")
    for _, row in rows.iterrows():
        builder.month(row[["month", *TURNOVER_COLUMNS]])
    start = rows["month"].min().date()
    end = (rows["month"].max() + pd.offsets.MonthEnd(0)).date()
    return onec.write(builder.client["account"], start, end, builder.documents, pd.Timestamp(as_of).date())


def main() -> None:
    parser = argparse.ArgumentParser(description="Выписки 1С для компаний демо-среза")
    parser.add_argument("--demo", type=Path, default=Path("../mocks/datasets/demo"))
    parser.add_argument("--out", type=Path, default=Path("../mocks/statements"))
    parser.add_argument("--inn", nargs="+", required=True)
    args = parser.parse_args()
    companies = pd.read_parquet(args.demo / "companies.parquet").set_index("inn")
    persons = pd.read_parquet(args.demo / "persons.parquet")
    monthly = pd.read_parquet(args.demo / "monthly.parquet")
    as_of = pd.read_parquet(args.demo / "applications.parquet")["application_date"].iloc[0]
    args.out.mkdir(parents=True, exist_ok=True)
    for inn in args.inn:
        org = companies.loc[inn]
        director = persons[(persons["application_id"] == org["application_id"]) & persons["is_director"]].iloc[0]
        rows = monthly[monthly["application_id"] == org["application_id"]]
        content = statement_file(rows, inn, org["name"], org["legal_form"],
                                 {"inn": director["inn"], "name": director["name"]}, as_of)
        path = args.out / f"{inn}.txt"
        path.write_bytes(content)
        print(f"{path}: {len(rows)} мес., {content.decode('cp1251').count('КонецДокумента')} платёжек")


if __name__ == "__main__":
    main()
