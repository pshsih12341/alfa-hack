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
}

ALLOWED_TERM_MONTHS = {6, 12, 18, 24, 30, 36}


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


class MaxByTermItem(BaseModel):
    termMonths: int
    maxSum: int
    rate: float
    monthlyPayment: int


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
    offers: list[OfferInfo] | None = None
    maxByTerm: list[MaxByTermItem] | None = None
    limit: LimitRange | None = None
    termLimit: TermLimit | None = None
    clientMessage: str | None = None


class AdditionalInfoRequest(BaseModel):
    actualAddress: str
    employeesCount: int
    website: str
    activityDescription: str


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