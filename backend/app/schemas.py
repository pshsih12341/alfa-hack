import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def normalize_phone_number(phone: str) -> str:
    """Нормализуем: берём 11 цифр, обязательно с 7 слева -> +7..."""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) != 11 or not digits.startswith("7"):
        raise ValueError("Номер телефона должен содержать 11 цифр и начинаться с 7")
    return "+" + digits


class RegisterRequest(BaseModel):
    phoneNumber: str
    creditSum: int = Field(ge=0)
    purpose: str = Field(min_length=1)
    income: int = Field(ge=0)
    inn: str = Field(default="", min_length=1, max_length=20)

    @field_validator("phoneNumber")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)


class LoginRequest(BaseModel):
    phoneNumber: str

    @field_validator("phoneNumber")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)


class RegisterResponse(BaseModel):
    clientId: str


class LoginResponse(BaseModel):
    clientId: str
    isAdmin: bool


class UserResponse(BaseModel):
    clientId: str
    phoneNumber: str
    creditSum: int
    purpose: str
    income: int
    inn: str
    isAdmin: bool
    createdAt: datetime
