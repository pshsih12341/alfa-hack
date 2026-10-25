from sqlalchemy import Boolean, DateTime, ForeignKey, Float, Integer, String, Text, JSON, Date
from sqlalchemy.orm import declarative_base, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
import uuid

from .database import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id = mapped_column(String(36), primary_key=True)  # clientId
    phone_number = mapped_column(String(20), unique=True, index=True, nullable=False)
    company_name = mapped_column(String(255), nullable=True)
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


class Product(Base):
    __tablename__ = "products"

    id = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(String(50), unique=True, nullable=False, index=True)
    product_name = mapped_column(String(255), nullable=False)
    purpose = mapped_column(JSON, nullable=False, default=list)
    rate = mapped_column(Float, nullable=False)
    limit_min = mapped_column(Integer, nullable=False)
    limit_max = mapped_column(Integer, nullable=False)
    term_min = mapped_column(Integer, nullable=False)
    term_max = mapped_column(Integer, nullable=False)
    term_step = mapped_column(Integer, nullable=False)
    business_type = mapped_column(String(50), nullable=False)
    with_collateral = mapped_column(Boolean, nullable=False)


class Application(Base):
    __tablename__ = "applications"
    from sqlalchemy.orm import relationship
    # в классе Application:
    client = relationship("User", lazy="joined")

    id = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    number = mapped_column(Integer, nullable=False)
    status = mapped_column(String(50), nullable=False, default="PRESCORING")
    credit_sum = mapped_column(Integer, nullable=False)
    purpose = mapped_column(String(1000), nullable=False)
    product_id = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)
    approved_limit = mapped_column(Integer, nullable=True)
    amount = mapped_column(Integer, nullable=True)
    term_months = mapped_column(Integer, nullable=True)
    rate = mapped_column(Float, nullable=True)
    bank_name = mapped_column(String(255), nullable=True)
    bic = mapped_column(String(20), nullable=True)
    account_number = mapped_column(String(50), nullable=True)
    additional_info = mapped_column(JSON, nullable=True)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    revenue_last_12m = mapped_column(Integer, nullable=True)
    bki_consent = mapped_column(Boolean, nullable=True)
    bki_consent_at = mapped_column(DateTime(timezone=True), nullable=True)
    refinance_loan_ids = mapped_column(JSON, nullable=True, default=list)
    scoring_response = mapped_column(JSON, nullable=True)

class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    status = mapped_column(String(50), nullable=False)
    created_at = mapped_column(DateTime, nullable=False, default=utcnow)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, index=True)
    number = mapped_column(String(50), nullable=False)
    date = mapped_column(Date, nullable=False)
    amount = mapped_column(Integer, nullable=False)
    recipient = mapped_column(String(255), nullable=False)
    recipient_account = mapped_column(String(50), nullable=False)
