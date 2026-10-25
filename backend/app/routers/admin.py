from datetime import date, datetime, time as dtime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import models
from ..auth import get_current_user
from ..database import SessionLocal
from ..models import Application
from ..schemas import (
    AdminApplicationDetails,
    AdminApplicationListResponse,
    AdminApplicationShort,
    AdminCompleteResponse,
    AdminPaymentOrderOut,
    AdminProductOut,
    AdminStatusHistoryOut,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Только для администратора")
    return user


@router.get("/applications", response_model=AdminApplicationListResponse)
def list_applications(
    dateFrom: date | None = Query(default=None),
    dateTo: date | None = Query(default=None),
    _admin: models.User = Depends(get_current_admin),
):
    with SessionLocal() as db:
        stmt = (
            select(Application)
            .options(selectinload(Application.client))
            .order_by(Application.created_at.desc())
        )
        if dateFrom is not None:
            stmt = stmt.where(
                Application.created_at >= datetime.combine(dateFrom, dtime.min, tzinfo=timezone.utc)
            )
        if dateTo is not None:
            stmt = stmt.where(
                Application.created_at <= datetime.combine(dateTo, dtime.max, tzinfo=timezone.utc)
            )
        rows = db.execute(stmt).scalars().all()
        items = [
            AdminApplicationShort(
                id=str(a.id),
                clientId=a.client_id,
                clientName=(
                    a.client.company_name 
                    if a.client and a.client.company_name 
                    else (a.client.phone_number if a.client else "")
                ),
                phoneNumber=a.client.phone_number if a.client else "",
                inn=a.client.inn if a.client else "",
                status=a.status,
                purpose=a.purpose,
                creditSum=a.credit_sum,
                createdAt=a.created_at,
                updatedAt=a.updated_at,
            )
            for a in rows
        ]
    return AdminApplicationListResponse(items=items)


@router.get("/applications/{application_id}", response_model=AdminApplicationDetails)
def get_application(
    application_id: str,
    _admin: models.User = Depends(get_current_admin),
):
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    with SessionLocal() as db:
        application = db.get(Application, app_uuid)
        if application is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        client = db.get(models.User, application.client_id)
        payment_orders = db.execute(
            select(models.PaymentOrder).where(
                models.PaymentOrder.application_id == application.id
            )
        ).scalars().all()
        history = db.execute(
            select(models.ApplicationStatusHistory)
            .where(models.ApplicationStatusHistory.application_id == application.id)
            .order_by(models.ApplicationStatusHistory.created_at.asc())
        ).scalars().all()

        # --- Логика сбора данных о продукте, ставке и сроке ---
        # 1. Берем из БД (если accept уже был)
        product_name = None
        product_rate = application.rate
        term_months = application.term_months or application.requested_term_months

        if application.product_id:
            product = db.get(models.Product, application.product_id)
            if product:
                product_name = product.product_name
                if product_rate is None:
                    product_rate = float(product.rate)

        # 2. Если в БД нет (статусы OFFER, REJECTED, INFO) — берем из scoring_response (ML)
        sr = application.scoring_response or {}
        
        if product_name is None and sr.get("product"):
            p_code = sr.get("product")
            # ML отдает код no_collateral, мапим на красивое имя
            if p_code == "no_collateral":
                product_name = "Кредит для бизнеса без залога"
            else:
                product_name = str(p_code)
                
        if product_rate is None and sr.get("rate"):
            product_rate = float(sr["rate"])
            
        if term_months is None and sr.get("termMonths"):
            term_months = int(sr["termMonths"])

        admin_product = AdminProductOut(product=product_name, rate=product_rate) if product_name else None

        return AdminApplicationDetails(
            id=str(application.id),
            clientId=application.client_id,
            clientName=client.company_name if client and client.company_name else (client.phone_number if client else ""),
            phoneNumber=client.phone_number if client else "",
            inn=client.inn if client else "",
            status=application.status,
            purpose=application.purpose,
            creditSum=application.credit_sum,
            createdAt=application.created_at,
            updatedAt=application.updated_at,
            product=admin_product,
            approvedLimit=application.approved_limit,
            termMonths=term_months,
            rate=product_rate,
            paymentOrders=[
                AdminPaymentOrderOut(
                    id=str(p.id),
                    number=p.number,
                    date=p.date,
                    amount=p.amount,
                    recipient=p.recipient,
                    recipientAccount=p.recipient_account,
                )
                for p in payment_orders
            ],
            statusHistory=[
                AdminStatusHistoryOut(status=h.status, createdAt=h.created_at)
                for h in history
            ],
        )


@router.post(
    "/applications/{application_id}/complete",
    response_model=AdminCompleteResponse,
)
def complete(
    application_id: str,
    _admin: models.User = Depends(get_current_admin),
):
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    with SessionLocal() as db:
        application = db.get(Application, app_uuid)
        if application is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if application.status != "AWAITING_DISBURSEMENT":
            raise HTTPException(status_code=409, detail="Статус не AWAITING_DISBURSEMENT")

        application.status = "COMPLETED"
        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status="COMPLETED"
            )
        )
        db.commit()
        db.refresh(application)
        return AdminCompleteResponse(
            id=str(application.id),
            status=application.status,
            updatedAt=application.updated_at,
        )


@router.post(
    "/applications/{application_id}/status",
    response_model=AdminStatusUpdateResponse,
    include_in_schema=False,
)
def force_status(
    application_id: str,
    payload: AdminStatusUpdateRequest,
    _admin: models.User = Depends(get_current_admin),
):
    """Demo-инструмент: принудительно перевести заявку в любой статус."""
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    allowed = {
        "PRESCORING", "SCORING", "INFO", "SUCCESS", "REJECTED",
        "AWAITING_DISBURSEMENT", "COMPLETED", "OFFER"
    }
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Недопустимый статус")

    with SessionLocal() as db:
        application = db.get(Application, app_uuid)
        if application is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        application.status = payload.status
        if payload.status == "SUCCESS" and application.product_id is None:
            no_col = db.execute(
                select(models.Product).where(models.Product.code == "no_collateral")
            ).scalar_one_or_none()
            if no_col is not None:
                application.product_id = no_col.id
                
        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status=payload.status
            )
        )
        db.commit()
        db.refresh(application)
        return AdminStatusUpdateResponse(
            id=str(application.id),
            status=application.status,
            updatedAt=application.updated_at,
        )