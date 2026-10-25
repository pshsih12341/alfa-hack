"""HTTP-сервис скоринга: решение по заявке, карточка компании и её кредиты из баз-моков.

Запуск: uvicorn alfa_ml.service.app:app --host 0.0.0.0 --port 8001
Контракт POST /score согласован с бэкендом. Этап 1 — без выписок; этап 2 — с оборотами
по счёту в Альфе (useAlfaAccount) и/или выписками из других банков (statements, файлы 1С).
"""
import base64
import binascii
import datetime as dt
import json
import logging
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import Engine, text

from alfa_ml.artifacts import load_seasonality
from alfa_ml.config import load_config
from alfa_ml.decision.heuristic import MODEL2_VERSION, MODEL_VERSION
from alfa_ml.decision.stage1 import Application, Decision, Option, RevenueRequired, decide_stage1, product
from alfa_ml.decision.stage2 import decide_stage2
from alfa_ml.features.build import okved_group, revenue_source
from alfa_ml.inn import is_valid_inn
from alfa_ml.service.db import make_engine, snapshot_date
from alfa_ml.service.settings import Settings
from alfa_ml.sources.read import SourceData, read_sources
from alfa_ml.statements.categorize import categorize, client_share, combine, monthly_aggregates
from alfa_ml.statements.onec import StatementFormatError, parse

MAX_STATEMENT_FILES = 5
MAX_STATEMENT_BYTES = 5 * 1024 * 1024
MIN_CLIENT_SHARE = 0.9  # доля платёжек с ИНН клиента: меньше — выписка не этого клиента

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
decision_log = logging.getLogger("alfa_ml.decisions")


class ApiModel(BaseModel):
    """Поля в JSON — camelCase, как в остальном API."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Person(ApiModel):
    inn: str
    name: str
    share: float | None = None


class CompanyCard(ApiModel):
    inn: str
    ogrn: str
    legal_form: str  # ip | ooo
    name: str
    registration_date: dt.date
    status: str  # active, liquidating, reorganizing, excluded, ceased
    is_active: bool
    okved_code: str
    okved_group: str
    director: Person  # у ИП — сам предприниматель
    participants: list[Person]  # участники ООО с долями; у ИП пусто
    is_alfa_client: bool
    revenue_known: bool  # False — выручку за 12 месяцев нужно спросить в анкете
    revenue_source: str | None  # alfa_full | alfa_partial | fns; None — только из анкеты


class Loan(ApiModel):
    loan_id: int
    lender: str
    balance: float  # остаток долга
    monthly_payment: float
    remaining_months: int
    end_date: dt.date  # дата среза + оставшиеся месяцы


class LoansResponse(ApiModel):
    inn: str
    loans: list[Loan]


class Health(ApiModel):
    status: str  # ok | degraded
    database: str  # ok | error
    as_of: dt.date | None
    model_version: str | None = None


class StatementFile(ApiModel):
    file_name: str
    content: str  # base64 выгрузки 1С


class ScoreRequest(ApiModel):
    application_id: str
    inn: str
    credit_sum: int
    term_months: int
    purpose: str
    refinance_loan_ids: list[int] = []
    has_collateral: bool = False  # клиент готов предоставить залог: продукт collateral, ставки ниже
    # Имя задано явно: генератор псевдонимов сделал бы revenueLast12M, а в контракте revenueLast12m.
    revenue_last12m: float | None = Field(default=None, gt=0, alias="revenueLast12m")  # None — есть в источниках
    bki_consent: bool
    use_alfa_account: bool = False  # этап 2
    statements: list[StatementFile] | None = None  # этап 2


class OfferOut(ApiModel):
    credit_sum: int
    term_months: int
    rate: float  # % годовых
    monthly_payment: int


class TermMax(ApiModel):
    term_months: int
    max_sum: int | None  # None — на этом сроке не проходит даже минимальная сумма
    rate: float | None
    monthly_payment: int | None


class Limits(ApiModel):
    min: int
    max: int
    step: int


class ScoreResponse(ApiModel):
    decision: Literal["APPROVED", "OFFER", "INFO", "REJECTED"]
    stage: int
    product: str | None
    pd: float | None
    rate: float | None  # % годовых: одобренного или первого предложенного варианта
    approved: OfferOut | None
    offers: list[OfferOut]
    max_by_term: list[TermMax]
    limit: Limits
    term_limit: Limits
    documents_required: list[str] | None  # bankStatements | alfaAccountConsent
    client_message: str  # для клиента
    reasons: list[str]  # для лога и сотрудника банка
    stop_rules: list[str]
    model_version: str


def _offer_out(option: Option | None) -> OfferOut | None:
    if option is None:
        return None
    return OfferOut(credit_sum=option.credit_sum, term_months=option.term_months,
                    rate=round(option.rate * 100, 2), monthly_payment=option.monthly_payment)


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or make_engine(settings.database_url)
    scoring_cfg = load_config("scoring")
    rules_cfg = load_config("rules")
    seasonality = load_seasonality(scoring_cfg)
    terms = scoring_cfg["terms_months"]
    amount_limit = Limits(min=scoring_cfg["min_amount"], max=scoring_cfg["max_amount"], step=scoring_cfg["amount_step"])
    term_limit = Limits(min=terms[0], max=terms[-1], step=terms[1] - terms[0])
    app = FastAPI(title="Скоринг МСБ", version="0.1.0",
                  description="Карточка компании и кредиты по ИНН из баз-моков; скоринг заявок — POST /score.")
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET", "POST"], allow_headers=["*"])
    as_of_cache: dict[str, dt.date | None] = {}

    def as_of(conn) -> dt.date | None:
        """Дата расчёта: из настроек, иначе дата среза моков (запоминается после первого чтения)."""
        if settings.as_of:
            return dt.date.fromisoformat(settings.as_of)
        if as_of_cache.get("value") is None:
            as_of_cache["value"] = snapshot_date(conn)
        return as_of_cache["value"]

    def load(inn: str) -> tuple[SourceData, dt.date]:
        if not is_valid_inn(inn):
            raise HTTPException(status_code=422, detail="Некорректный ИНН: нужно 10 или 12 цифр с верными контрольными")
        with engine.connect() as conn:
            date = as_of(conn)
            data = read_sources(conn, inn, date,
                                inquiries_window_days=scoring_cfg["features"]["inquiries_window_days"])
        if data is None:
            raise HTTPException(status_code=404, detail="Организация не найдена в ЕГРЮЛ/ЕГРИП")
        return data, date

    def validate(request: ScoreRequest) -> None:
        """Проверки заявки, которые не зависят от данных источников."""
        if not request.bki_consent:
            raise HTTPException(status_code=422, detail="Без согласия на запрос в БКИ скоринг невозможен")
        if request.statements and len(request.statements) > MAX_STATEMENT_FILES:
            raise HTTPException(status_code=422, detail=f"Не больше {MAX_STATEMENT_FILES} файлов выписок")
        if request.term_months not in terms:
            raise HTTPException(status_code=422, detail=f"Срок должен быть одним из {terms} месяцев")
        if not amount_limit.min <= request.credit_sum <= amount_limit.max:
            raise HTTPException(status_code=422,
                                detail=f"Сумма должна быть от {amount_limit.min} до {amount_limit.max} ₽")
        if request.purpose not in scoring_cfg["purposes"]:
            raise HTTPException(status_code=422, detail=f"Цель кредита должна быть одной из {scoring_cfg['purposes']}")
        if request.refinance_loan_ids and request.purpose != "refinancing":
            raise HTTPException(status_code=422, detail="refinanceLoanIds передаются только при purpose = refinancing")

    @app.get("/health", response_model=Health)
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return Health(status="ok", database="ok", as_of=as_of(conn),
                              model_version=f"{MODEL_VERSION}; {MODEL2_VERSION}")
        except Exception:
            body = Health(status="degraded", database="error", as_of=None)
            return JSONResponse(status_code=503, content=body.model_dump(mode="json", by_alias=True))

    @app.post("/score", response_model=ScoreResponse)
    def score(request: ScoreRequest):
        """Решение по заявке этапа 1: стоп-правила, PD, подбор суммы и срока, ставка по риску."""
        validate(request)
        data, date = load(request.inn)
        business = data.bki_loans.loc[data.bki_loans["is_business"], "loan_id"]
        unknown = set(request.refinance_loan_ids) - set(business.astype(int))
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"Кредитов {sorted(unknown)} нет среди бизнес-кредитов заёмщика в БКИ")
        application = Application(request.credit_sum, request.term_months, request.purpose,
                                   tuple(request.refinance_loan_ids), request.revenue_last12m, request.has_collateral)
        if request.use_alfa_account or request.statements:
            statements = statement_months(request, data, date)
            decision = decide_stage2(data, statements, application, date, scoring_cfg, rules_cfg, seasonality)
        else:
            try:
                decision = decide_stage1(data, application, date, scoring_cfg, rules_cfg)
            except RevenueRequired as error:
                raise HTTPException(status_code=422, detail=f"{error} (revenueLast12m)") from error
        response = _score_response(decision, product(application))
        decision_log.info(json.dumps({
            "applicationId": request.application_id, "inn": request.inn, "asOf": date.isoformat(),
            "decision": decision.decision, "pd": decision.pd, "stopRules": decision.stop_rules,
            "modelVersion": decision.model_version, "reasons": decision.reasons,
        }, ensure_ascii=False))
        return response

    def statement_months(request: ScoreRequest, data: SourceData, date: dt.date) -> pd.DataFrame:
        """Помесячные обороты для этапа 2: счёт в Альфе и/или файлы 1С из других банков, сложенные по месяцам."""
        parts = []
        if request.use_alfa_account:
            if not bool(data.companies["is_alfa_client"].iloc[0]):
                raise HTTPException(status_code=422, detail="useAlfaAccount — только для клиентов Альфы: "
                                                            "загрузите выписки файлами (statements)")
            parts.append(data.monthly)
        for file in request.statements or []:
            try:
                raw = base64.b64decode(file.content, validate=True)
            except (binascii.Error, ValueError) as error:
                raise HTTPException(status_code=422, detail=f"{file.file_name}: content — не base64") from error
            if len(raw) > MAX_STATEMENT_BYTES:
                raise HTTPException(status_code=422, detail=f"{file.file_name}: файл больше 5 МБ")
            try:
                statement = parse(raw)
            except StatementFormatError as error:
                raise HTTPException(status_code=422, detail=f"{file.file_name}: {error}") from error
            if client_share(statement, request.inn) < MIN_CLIENT_SHARE:
                raise HTTPException(status_code=422, detail=f"{file.file_name}: выписка не по счёту этого клиента")
            parts.append(monthly_aggregates(categorize(statement, request.inn), 0, date))
        return combine(*parts)

    def _score_response(decision: Decision, product_key: str) -> ScoreResponse:
        approved = _offer_out(decision.approved)
        offers = [_offer_out(option) for option in decision.offers]
        chosen = approved or (offers[0] if offers else None)
        return ScoreResponse(
            decision=decision.decision, stage=decision.stage,
            product=product_key if decision.decision in ("APPROVED", "OFFER") else None,
            pd=None if decision.pd is None else round(decision.pd, 4),
            rate=chosen.rate if chosen else None,
            approved=approved, offers=offers,
            max_by_term=[TermMax(term_months=months, max_sum=o.credit_sum if o else None,
                                 rate=round(o.rate * 100, 2) if o else None,
                                 monthly_payment=o.monthly_payment if o else None)
                         for months, o in decision.max_by_term],
            limit=amount_limit, term_limit=term_limit,
            documents_required=decision.documents_required, client_message=decision.client_message,
            reasons=decision.reasons, stop_rules=decision.stop_rules, model_version=decision.model_version,
        )

    @app.get("/companies/{inn}", response_model=CompanyCard)
    def company(inn: str):
        """Карточка для анкеты: данные реестра и нужно ли спрашивать выручку."""
        data, _ = load(inn)
        org = data.companies.iloc[0]
        roles = data.persons
        director = roles[roles["is_director"]].iloc[0]
        participants = roles[roles["share"] > 0] if org["legal_form"] == "ooo" else roles.iloc[0:0]
        source = revenue_source([org["is_alfa_client"]], [len(data.monthly)], [org["fns_revenue"]],
                                scoring_cfg["features"]["revenue_min_months"])[0]
        return CompanyCard(
            inn=org["inn"], ogrn=org["ogrn"], legal_form=org["legal_form"], name=org["name"],
            registration_date=org["registration_date"].date(), status=org["status"],
            is_active=org["status"] == "active", okved_code=org["okved_code"],
            okved_group=okved_group(data.companies["okved_code"], scoring_cfg["okved_groups"]).iloc[0],
            director=Person(inn=director["inn"], name=director["name"]),
            participants=[Person(inn=p["inn"], name=p["name"], share=round(float(p["share"]), 4))
                          for _, p in participants.iterrows()],
            is_alfa_client=bool(org["is_alfa_client"]),
            revenue_known=source != "declared",
            revenue_source=None if source == "declared" else str(source),
        )

    @app.get("/companies/{inn}/loans", response_model=LoansResponse)
    def company_loans(inn: str):
        """Действующие бизнес-кредиты из БКИ — для выбора при рефинансировании.

        Это данные кредитной истории: показывать клиенту только после согласия на запрос в БКИ.
        """
        data, date = load(inn)
        loans = data.bki_loans[data.bki_loans["is_business"]].sort_values("balance", ascending=False)
        return LoansResponse(inn=inn, loans=[
            Loan(loan_id=int(l["loan_id"]), lender=l["lender"], balance=float(l["balance"]),
                 monthly_payment=float(l["monthly_payment"]), remaining_months=int(l["remaining_months"]),
                 end_date=(pd.Timestamp(date) + pd.DateOffset(months=int(l["remaining_months"]))).date())
            for _, l in loans.iterrows()
        ])

    return app


app = create_app()
