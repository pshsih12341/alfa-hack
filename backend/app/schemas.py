from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


ALLOWED_PURPOSES = {
    "real_estate",
    "equipment",
    "repair",
    "working_capital",
    "current_expenses",
    "refinancing",
    "property",
}

ALLOWED_TERM_MONTHS = {6, 12, 18, 24, 30, 36}

# Лимиты суммы — как в ML-сервисе (ml/config/scoring.yaml): вне их ML отвечает 422.
CREDIT_SUM_MIN = 100_000
CREDIT_SUM_MAX = 30_000_000

# Выписки этапа 2 — как в ML-сервисе: не больше 5 файлов.
MAX_STATEMENT_FILES = 5


# ---------- Auth ----------

class RegisterRequest(BaseModel):
    phoneNumber: str
    inn: str = Field(min_length=10, max_length=12)
    creditSum: int = Field(ge=0)
    purpose: str
    termMonths: int
    revenueLast12m: int | None = Field(default=None, ge=0)
    bkiConsent: bool
    refinanceLoanIds: list[int] = Field(default_factory=list)
    companyName: str | None = None
    hasCollateral: bool = False


class LoginRequest(BaseModel):
    phoneNumber: str


class RegisterResponse(BaseModel):
    clientId: str
    applicationId: str
    isAdmin: bool


class LoginResponse(BaseModel):
    clientId: str
    isAdmin: bool


class UserResponse(BaseModel):
    clientId: str
    phoneNumber: str
    inn: str
    isAdmin: bool
    createdAt: datetime


# ---------- Applications ----------

class ApplicationShort(BaseModel):
    id: str
    number: int
    status: str
    creditSum: int
    purpose: str
    createdAt: datetime
    updatedAt: datetime


class ApplicationListResponse(BaseModel):
    items: list[ApplicationShort]


class ApplicationCreateRequest(BaseModel):
    creditSum: int = Field(ge=0)
    purpose: str
    termMonths: int
    hasCollateral: bool = False
    revenueLast12m: int | None = Field(default=None, ge=0)
    # None — взять согласие из прошлой заявки клиента (дано при регистрации).
    bkiConsent: bool | None = None
    refinanceLoanIds: list[int] = Field(default_factory=list)


class LimitRange(BaseModel):
    min: int
    max: int
    step: int | None = None

class TermLimit(BaseModel):
    min: int
    max: int
    step: int


class ProductInfo(BaseModel):
    product: str
    purpose: list[str]
    rate: float
    limit: LimitRange
    termLimit: TermLimit
    businessType: str
    withCollateral: bool


class OfferInfo(BaseModel):
    creditSum: int
    termMonths: int
    rate: float
    monthlyPayment: int
    product: str | None = None   

class MaxByTermItem(BaseModel):
    termMonths: int
    # None — на этом сроке не проходит даже минимальная сумма: срок недоступен.
    # Обязательными эти поля делать нельзя: на таких заявках деталь падает с 500.
    maxSum: int | None = None
    rate: float | None = None
    monthlyPayment: int | None = None
    product: str | None = None


class ApplicationDetails(BaseModel):
    id: str
    number: int
    clientId: str
    status: str
    creditSum: int
    purpose: str
    createdAt: datetime
    updatedAt: datetime
    products: list[ProductInfo] | None = None
    additionalInfo: dict[str, Any] | None = None
    amount: int | None = None
    termMonths: int | None = None
    rate: float | None = None
    approvedLimit: int | None = None
    approved: OfferInfo | None = None  # SUCCESS: одобренные условия
    offers: list[OfferInfo] | None = None
    maxByTerm: list[MaxByTermItem] | None = None
    limit: LimitRange | None = None
    termLimit: TermLimit | None = None
    clientMessage: str | None = None
    # INFO и OFFER: что нужно для этапа 2 — alfaAccountConsent (счёт в Альфе) или bankStatements (файлы 1С).
    documentsRequired: list[str] | None = None


class StatementFile(BaseModel):
    fileName: str
    content: str  # base64 выгрузки 1С


class AdditionalInfoRequest(BaseModel):
    """Этап 2: обороты по счёту в Альфе и/или выписки других банков файлами."""
    useAlfaAccount: bool = False
    statements: list[StatementFile] = Field(default_factory=list, max_length=MAX_STATEMENT_FILES)


class AdditionalInfoResponse(BaseModel):
    id: str
    status: str
    updatedAt: datetime


class AcceptRequest(BaseModel):
    amount: int
    termMonths: int
    bankName: str
    bic: str
    accountNumber: str


class AcceptResponse(BaseModel):
    id: str
    status: str
    amount: int
    termMonths: int
    rate: float
    updatedAt: datetime


class AcceptOfferRequest(BaseModel):
    creditSum: int
    termMonths: int
    bankName: str
    bic: str
    accountNumber: str


# ---------- Admin ----------

class AdminApplicationShort(BaseModel):
    id: str
    clientId: str
    clientName: str
    phoneNumber: str
    inn: str
    status: str
    purpose: str
    creditSum: int
    createdAt: datetime
    updatedAt: datetime


class AdminApplicationListResponse(BaseModel):
    items: list[AdminApplicationShort]


class AdminProductOut(BaseModel):
    product: str
    rate: float


class AdminPaymentOrderOut(BaseModel):
    id: str
    number: str
    date: date
    amount: int
    recipient: str
    recipientAccount: str


class AdminStatusHistoryOut(BaseModel):
    status: str
    createdAt: datetime


class AdminApplicationDetails(BaseModel):
    id: str
    clientId: str
    clientName: str
    phoneNumber: str
    inn: str
    status: str
    purpose: str
    creditSum: int
    createdAt: datetime
    updatedAt: datetime
    product: AdminProductOut | None = None
    approvedLimit: int | None = None
    termMonths: int | None = None  
    rate: float | None = None         
    paymentOrders: list[AdminPaymentOrderOut]
    statusHistory: list[AdminStatusHistoryOut]


class AdminCompleteResponse(BaseModel):
    id: str
    status: str
    updatedAt: datetime


class AdminStatusUpdateRequest(BaseModel):
    status: str


class AdminStatusUpdateResponse(BaseModel):
    id: str
    status: str
    updatedAt: datetime