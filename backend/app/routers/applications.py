import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from .. import models
from ..auth import get_current_user
from ..database import SessionLocal, utcnow
from ..scoring import run_scoring
from ..schemas import (
    CREDIT_SUM_MIN,
    AcceptOfferRequest,
    AcceptRequest,
    AcceptResponse,
    AdditionalInfoRequest,
    AdditionalInfoResponse,
    ApplicationCreateRequest,
    ApplicationDetails,
    ApplicationListResponse,
    ApplicationShort,
    LimitRange,
    MaxByTermItem,
    OfferInfo,
    ProductInfo,
    TermLimit,
)
from ..validation import validate_application

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _product_to_info(product: models.Product) -> ProductInfo:
    return ProductInfo(
        product=product.product_name,
        purpose=list(product.purpose or []),
        rate=float(product.rate),
        limit=LimitRange(min=product.limit_min, max=product.limit_max),
        termLimit=TermLimit(
            min=product.term_min, max=product.term_max, step=product.term_step
        ),
        businessType=product.business_type,
        withCollateral=bool(product.with_collateral),
    )


def _short(application: models.Application) -> ApplicationShort:
    return ApplicationShort(
        id=str(application.id),
        number=application.number,
        status=application.status,
        creditSum=application.credit_sum,
        purpose=application.purpose,
        createdAt=application.created_at,
        updatedAt=application.updated_at,
    )


def _get_owned(db, application_id: str, user: models.User) -> models.Application:
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    application = db.get(models.Application, app_uuid)
    if application is None or application.client_id != user.id:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return application


def _product_by_code(db, code: str | None) -> models.Product | None:
    if not code:
        return None
    return db.execute(
        select(models.Product).where(models.Product.code == code)
    ).scalar_one_or_none()


def _public_info(info: dict | None) -> dict | None:
    """additionalInfo для клиента: без содержимого файлов выписок."""
    if not info:
        return None
    return {
        "useAlfaAccount": bool(info.get("useAlfaAccount")),
        "statements": [{"fileName": s.get("fileName")} for s in info.get("statements") or []],
    }


@router.get("", response_model=ApplicationListResponse)
def list_applications(user: models.User = Depends(get_current_user)):
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(models.Application)
                .where(models.Application.client_id == user.id)
                .order_by(models.Application.created_at.asc())
            )
            .scalars()
            .all()
        )
    return ApplicationListResponse(items=[_short(a) for a in rows])


@router.post("", response_model=ApplicationShort, status_code=201)
def create_application(
    payload: ApplicationCreateRequest,
    background: BackgroundTasks,
    user: models.User = Depends(get_current_user),
):
    validate_application(payload.creditSum, payload.purpose, payload.termMonths, payload.refinanceLoanIds)

    with SessionLocal() as db:
        # Согласие на БКИ: из запроса, а если его нет — из прошлых заявок клиента (дано при регистрации).
        consent = payload.bkiConsent
        if consent is None:
            consent = db.execute(
                select(models.Application.bki_consent)
                .where(models.Application.client_id == user.id)
                .where(models.Application.bki_consent.is_(True))
                .limit(1)
            ).scalar_one_or_none()
        if not consent:
            raise HTTPException(status_code=400, detail="Требуется согласие на запрос в БКИ")

        last_number = db.execute(
            select(models.Application.number)
            .where(models.Application.client_id == user.id)
            .order_by(models.Application.number.desc())
            .limit(1)
        ).scalar_one_or_none()
        next_number = (last_number or 0) + 1

        application = models.Application(
            client_id=user.id,
            number=next_number,
            status="PRESCORING",
            credit_sum=payload.creditSum,
            purpose=payload.purpose,
            requested_term_months=payload.termMonths,
            has_collateral=payload.hasCollateral,
            revenue_last_12m=payload.revenueLast12m or None,  # 0 — выручка не указана
            bki_consent=True,
            bki_consent_at=utcnow(),
            refinance_loan_ids=payload.refinanceLoanIds,
        )
        db.add(application)
        db.flush()
        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status="PRESCORING"
            )
        )
        db.commit()
        db.refresh(application)
        application_id = str(application.id)
        result = _short(application)

    background.add_task(run_scoring, application_id)
    return result


@router.get("/{application_id}", response_model=ApplicationDetails)
def get_application(
    application_id: str,
    user: models.User = Depends(get_current_user),
):
    with SessionLocal() as db:
        application = _get_owned(db, application_id, user)

        products = None
        if application.status == "SUCCESS":
            if application.product_id is not None:
                selected = db.get(models.Product, application.product_id)
                products = [_product_to_info(selected)] if selected else None

        offers = None
        max_by_term = None
        limit_range = None
        term_limit_range = None
        client_message = None
        
        if application.status == "OFFER" and application.scoring_response:
            sr = application.scoring_response
            
            p_code = sr.get("product", "no_collateral")
            if p_code == "collateral":
                p_name = "Кредит для бизнеса под залог"
            else:
                p_name = "Кредит для бизнеса без залога"

            if sr.get("offers"):
                offers = [OfferInfo(**{**o, "product": p_name}) for o in sr["offers"]]
            
            if sr.get("maxByTerm"):
                max_by_term = [MaxByTermItem(**{**m, "product": p_name}) for m in sr["maxByTerm"]]
            
            if sr.get("limit"):
                limit_range = LimitRange(**sr["limit"])
            
            if sr.get("termLimit"):
                term_limit_range = TermLimit(**sr["termLimit"])
            
            client_message = sr.get("clientMessage")
            
        return ApplicationDetails(
            id=str(application.id),
            number=application.number,
            clientId=application.client_id,
            status=application.status,
            creditSum=application.credit_sum,
            purpose=application.purpose,
            createdAt=application.created_at,
            updatedAt=application.updated_at,
            products=products,
            additionalInfo=application.additional_info,
            amount=application.amount,
            termMonths=application.term_months,
            rate=application.rate,
            approvedLimit=application.approved_limit,
            offers=offers,
            maxByTerm=max_by_term,
            limit=limit_range,
            termLimit=term_limit_range,
            clientMessage=client_message,
        )

@router.post(
    "/{application_id}/additional-info",
    response_model=AdditionalInfoResponse,
)
def submit_additional_info(
    application_id: str,
    payload: AdditionalInfoRequest,
    background: BackgroundTasks,
    user: models.User = Depends(get_current_user),
):
    """Этап 2: обороты по счёту в Альфе и/или выписки файлами — заявка уходит на повторный скоринг."""
    if not payload.useAlfaAccount and not payload.statements:
        raise HTTPException(
            status_code=400,
            detail="Разрешите использовать данные счёта в Альфе или загрузите выписки",
        )
    with SessionLocal() as db:
        application = _get_owned(db, application_id, user)
        if application.status not in ("INFO", "OFFER"):
            raise HTTPException(status_code=400, detail="Выписки принимаются только для заявок в статусе INFO или OFFER")

        application.additional_info = {
            "useAlfaAccount": payload.useAlfaAccount,
            "statements": [s.model_dump() for s in payload.statements],
        }
        application.status = "PRESCORING"
        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status="PRESCORING"
            )
        )
        db.commit()
        db.refresh(application)
        response = AdditionalInfoResponse(
            id=str(application.id),
            status=application.status,
            updatedAt=application.updated_at,
        )

    background.add_task(run_scoring, application_id)
    return response


@router.post("/{application_id}/accept", response_model=AcceptResponse)
def accept(
    application_id: str,
    payload: AcceptRequest,
    user: models.User = Depends(get_current_user),
):
    with SessionLocal() as db:
        application = _get_owned(db, application_id, user)
        if application.status != "SUCCESS":
            raise HTTPException(status_code=409, detail="Статус не SUCCESS")

        sr = application.scoring_response or {}
        if sr.get("maxByTerm"):
            # Решение ML: сумма не больше одобренной на выбранный срок, ставка — этого срока.
            item = next((m for m in sr["maxByTerm"] if m.get("termMonths") == payload.termMonths), None)
            if item is None or item.get("maxSum") is None:
                raise HTTPException(status_code=400, detail="На этот срок кредит не одобрен")
            limit_min = (sr.get("limit") or {}).get("min", CREDIT_SUM_MIN)
            if not limit_min <= payload.amount <= item["maxSum"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"На {payload.termMonths} мес. можно взять от {limit_min} до {item['maxSum']} ₽",
                )
            approved = sr.get("approved") or {}
            same = approved.get("creditSum") == payload.amount and approved.get("termMonths") == payload.termMonths
            application.rate = float(approved["rate"] if same else item["rate"])
        else:
            # Без ответа ML (mock-скоринг) — лимиты продукта.
            if application.product_id is None:
                raise HTTPException(status_code=409, detail="Продукт не выбран")
            product = db.get(models.Product, application.product_id)
            if product is None:
                raise HTTPException(status_code=409, detail="Продукт не найден")
            if not (product.limit_min <= payload.amount <= product.limit_max):
                raise HTTPException(status_code=400, detail="Сумма вне лимита")
            if not (product.term_min <= payload.termMonths <= product.term_max):
                raise HTTPException(status_code=400, detail="Срок вне лимита")
            if (payload.termMonths - product.term_min) % product.term_step != 0:
                raise HTTPException(status_code=400, detail="Срок не кратен шагу")
            if application.rate is None:
                application.rate = product.rate  # fallback, если ML не дал rate

        application.amount = payload.amount
        application.term_months = payload.termMonths
        application.bank_name = payload.bankName
        application.bic = payload.bic
        application.account_number = payload.accountNumber
        application.approved_limit = payload.amount
        application.status = "AWAITING_DISBURSEMENT"

        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status="AWAITING_DISBURSEMENT"
            )
        )
        db.add(
            models.PaymentOrder(
                application_id=application.id,
                number=str(application.number),
                date=date.today(),
                amount=payload.amount,
                recipient=user.company_name or user.phone_number,
                recipient_account=payload.accountNumber,
            )
        )
        db.commit()
        db.refresh(application)
        return AcceptResponse(
            id=str(application.id),
            status=application.status,
            amount=application.amount,
            termMonths=application.term_months,
            rate=float(application.rate),
            updatedAt=application.updated_at,
        )


@router.post("/{application_id}/accept-offer", response_model=AcceptResponse)
def accept_offer(
    application_id: str,
    payload: AcceptOfferRequest,
    user: models.User = Depends(get_current_user),
):
    with SessionLocal() as db:
        application = _get_owned(db, application_id, user)
        if application.status != "OFFER":
            raise HTTPException(status_code=409, detail="Статус не OFFER")
        if not application.scoring_response:
            raise HTTPException(status_code=409, detail="Нет данных предложения")

        sr = application.scoring_response
        offers = sr.get("offers") or []
        max_by_term = sr.get("maxByTerm") or []
        limit_min = (sr.get("limit") or {}).get("min", CREDIT_SUM_MIN)

        chosen = None
        for o in offers:
            if (
                o.get("creditSum") == payload.creditSum
                and o.get("termMonths") == payload.termMonths
            ):
                chosen = o
                break

        if chosen is None:
            # Своя сумма с ползунка: не больше максимума на этот срок; срок с maxSum = null недоступен.
            for m in max_by_term:
                if (
                    m.get("termMonths") == payload.termMonths
                    and m.get("maxSum") is not None
                    and limit_min <= payload.creditSum <= m["maxSum"]
                ):
                    chosen = m
                    break

        if chosen is None:
            raise HTTPException(
                status_code=400, detail="Выбранный вариант не из предложения"
            )

        rate = float(chosen.get("rate", 0))

        product = _product_by_code(db, sr.get("product"))
        if product is not None:
            application.product_id = product.id
        application.amount = payload.creditSum
        application.term_months = payload.termMonths
        application.rate = rate
        application.bank_name = payload.bankName
        application.bic = payload.bic
        application.account_number = payload.accountNumber
        application.approved_limit = payload.creditSum
        application.status = "AWAITING_DISBURSEMENT"

        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status="AWAITING_DISBURSEMENT"
            )
        )
        db.add(
            models.PaymentOrder(
                application_id=application.id,
                number=str(application.number),
                date=date.today(),
                amount=payload.creditSum,
                recipient=user.company_name or user.phone_number,
                recipient_account=payload.accountNumber,
            )
        )
        db.commit()
        db.refresh(application)
        return AcceptResponse(
            id=str(application.id),
            status=application.status,
            amount=application.amount,
            termMonths=application.term_months,
            rate=float(application.rate),
            updatedAt=application.updated_at,
        )
