from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, mapped_column

from .database import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id = mapped_column(String(36), primary_key=True)  # clientId
    phone_number = mapped_column(String(20), unique=True, index=True, nullable=False)
    credit_sum = mapped_column(Integer, nullable=False, default=0)
    purpose = mapped_column(Text, nullable=False, default="")
    income = mapped_column(Integer, nullable=False, default=0)
    inn = mapped_column(String(20), nullable=False, default="")
    is_admin = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id = mapped_column(String(36), primary_key=True)
    client_id = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    token = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at = mapped_column(DateTime, nullable=False)
