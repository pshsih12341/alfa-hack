"""HTTP-сервис скоринга: проверка состояния, карточка компании и её кредиты из баз-моков.

Запуск: uvicorn alfa_ml.service.app:app --host 0.0.0.0 --port 8001
POST /score — следующий шаг, по контракту, согласованному с бэкендом.
"""
import datetime as dt

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Engine, text

from alfa_ml.config import load_config
from alfa_ml.features.build import okved_group, revenue_source
from alfa_ml.inn import is_valid_inn
from alfa_ml.service.db import make_engine, snapshot_date
from alfa_ml.service.settings import Settings
from alfa_ml.sources.read import SourceData, read_sources


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
    balance: float
    monthly_payment: float
    remaining_months: int


class LoansResponse(ApiModel):
    inn: str
    loans: list[Loan]


class Health(ApiModel):
    status: str  # ok | degraded
    database: str  # ok | error
    as_of: dt.date | None
    model_version: str | None = None


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or make_engine(settings.database_url)
    scoring_cfg = load_config("scoring")
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

    def load(inn: str) -> SourceData:
        if not is_valid_inn(inn):
            raise HTTPException(status_code=422, detail="Некорректный ИНН: нужно 10 или 12 цифр с верными контрольными")
        with engine.connect() as conn:
            data = read_sources(conn, inn, as_of(conn),
                                inquiries_window_days=scoring_cfg["features"]["inquiries_window_days"])
        if data is None:
            raise HTTPException(status_code=404, detail="Организация не найдена в ЕГРЮЛ/ЕГРИП")
        return data

    @app.get("/health", response_model=Health)
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return Health(status="ok", database="ok", as_of=as_of(conn))
        except Exception:
            body = Health(status="degraded", database="error", as_of=None)
            return JSONResponse(status_code=503, content=body.model_dump(mode="json", by_alias=True))

    @app.get("/companies/{inn}", response_model=CompanyCard)
    def company(inn: str):
        """Карточка для анкеты: данные реестра и нужно ли спрашивать выручку."""
        data = load(inn)
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
        loans = load(inn).bki_loans
        loans = loans[loans["is_business"]].sort_values("balance", ascending=False)
        return LoansResponse(inn=inn, loans=[
            Loan(loan_id=int(l["loan_id"]), lender=l["lender"], balance=float(l["balance"]),
                 monthly_payment=float(l["monthly_payment"]), remaining_months=int(l["remaining_months"]))
            for _, l in loans.iterrows()
        ])

    return app


app = create_app()
