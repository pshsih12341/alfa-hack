"""Схема баз-моков, одна на SQLite (тесты, локальная проверка) и PostgreSQL (docker-compose).

Префикс таблицы — источник: egr_ (ЕГРЮЛ/ЕГРИП), efrsb_, rfm_, bki_, fns_, alfa_ (внутренние данные банка).
"""
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Date, Float, ForeignKey, Index, Integer,
                        MetaData, Numeric, PrimaryKeyConstraint, Table, Text)

metadata = MetaData()


def money() -> Numeric:
    """Деньги с копейками; читаются как float."""
    return Numeric(15, 2, asdecimal=False)


egr_organizations = Table(
    "egr_organizations", metadata,
    Column("inn", Text, primary_key=True),
    Column("ogrn", Text, nullable=False, unique=True),
    Column("legal_form", Text, CheckConstraint("legal_form IN ('ip', 'ooo')"), nullable=False),
    Column("name", Text, nullable=False),
    Column("registration_date", Date, nullable=False),
    Column("status", Text, nullable=False),  # active, liquidating, reorganizing, excluded, ceased
    Column("okved_code", Text, nullable=False),
    comment="ЕГРЮЛ / ЕГРИП: организации и ИП",
)

egr_roles = Table(
    "egr_roles", metadata,
    Column("org_inn", Text, ForeignKey("egr_organizations.inn"), nullable=False),
    Column("person_inn", Text, nullable=False),
    Column("person_name", Text, nullable=False),
    Column("is_director", Boolean, nullable=False),
    Column("share", Float(53), nullable=False),
    PrimaryKeyConstraint("org_inn", "person_inn"),
    comment="Кто стоит за организацией: ИП, директор, участники с долями",
)

egr_person_history = Table(
    "egr_person_history", metadata,
    Column("person_inn", Text, nullable=False),
    Column("org_inn", Text, nullable=False),
    Column("org_name", Text, nullable=False),
    Column("role", Text, nullable=False),  # director, participant, ip
    Column("start_date", Date, nullable=False),
    Column("end_date", Date),  # NULL — бизнес действует
    Column("outcome", Text, nullable=False),  # active, closed_voluntarily, excluded_by_fns, bankruptcy, closed_with_debts
    Index("egr_person_history_person", "person_inn"),
    comment="Другие бизнесы человека, прошлые и действующие, и чем они закончились",
)

efrsb_cases = Table(
    "efrsb_cases", metadata,
    Column("debtor_inn", Text, nullable=False),
    Column("debtor_type", Text, nullable=False),  # company, person
    Column("status", Text, nullable=False),  # in_progress, completed
    Column("start_date", Date, nullable=False),
    Column("end_date", Date),
    Index("efrsb_cases_debtor", "debtor_inn"),
    comment="ЕФРСБ: дела о банкротстве",
)

rfm_entries = Table(
    "rfm_entries", metadata,
    Column("inn", Text, primary_key=True),
    Column("entity_type", Text, nullable=False),  # company, person
    Column("added_date", Date, nullable=False),
    comment="Перечень Росфинмониторинга",
)

bki_subjects = Table(
    "bki_subjects", metadata,
    Column("inn", Text, primary_key=True),
    Column("subject_type", Text, nullable=False),  # company, person
    Column("has_history", Boolean, nullable=False),
    Column("max_dpd_24m", Integer),  # NULL — кредитной истории нет
    comment="БКИ: субъекты кредитных историй",
)

bki_inquiries = Table(
    "bki_inquiries", metadata,
    Column("inn", Text, nullable=False),
    Column("inquiry_date", Date, nullable=False),
    Column("lender", Text, nullable=False),
    Index("bki_inquiries_inn", "inn"),
    comment="БКИ: запросы кредитной истории другими кредиторами",
)

bki_loans = Table(
    "bki_loans", metadata,
    Column("loan_id", BigInteger, primary_key=True, autoincrement=False),
    Column("borrower_inn", Text, nullable=False),
    Column("lender", Text, nullable=False),
    Column("is_business", Boolean, nullable=False),
    Column("balance", money(), nullable=False),
    Column("monthly_payment", money(), nullable=False),
    Column("remaining_months", Integer, nullable=False),
    Index("bki_loans_borrower", "borrower_inn"),
    comment="БКИ: действующие кредиты",
)

fns_ens = Table(
    "fns_ens", metadata,
    Column("inn", Text, primary_key=True),
    Column("debt", money(), nullable=False),
    Column("as_of_date", Date, nullable=False),
    comment="ФНС: сальдо единого налогового счёта",
)

fns_financials = Table(
    "fns_financials", metadata,
    Column("inn", Text, nullable=False),
    Column("year", Integer, nullable=False),
    Column("revenue", money(), nullable=False),
    PrimaryKeyConstraint("inn", "year"),
    comment="ФНС: доходы организаций за год из открытых данных; у ИП их нет",
)

alfa_clients = Table(
    "alfa_clients", metadata,
    Column("inn", Text, primary_key=True),
    Column("client_since", Date, nullable=False),
    comment="Альфа: клиенты с расчётным счётом",
)

TURNOVER_COLUMNS = [
    "inflow_customers", "inflow_acquiring", "inflow_cash", "inflow_own_transfer", "inflow_loans",
    "inflow_owner_funding", "outflow_suppliers", "outflow_salary", "outflow_rent", "outflow_taxes",
    "outflow_other_debt", "outflow_own_transfer", "outflow_loan_payments", "outflow_owner_payouts",
    "top_customer_inflow",
]

alfa_turnover = Table(
    "alfa_turnover", metadata,
    Column("inn", Text, nullable=False),
    Column("month", Date, nullable=False),  # первый день месяца
    *[Column(name, money(), nullable=False) for name in TURNOVER_COLUMNS],
    PrimaryKeyConstraint("inn", "month"),
    comment="Альфа: помесячные обороты по счёту, суммы по категориям операций",
)
