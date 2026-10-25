import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .. import config, models
from ..auth import _set_auth_cookie, create_session, get_current_user, get_session_store
from ..database import SessionLocal, utcnow
from ..scoring import run_scoring
from ..schemas import (
    ALLOWED_PURPOSES,
    ALLOWED_TERM_MONTHS,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


@router.post("/reg", status_code=201)
def register(payload: RegisterRequest, background: BackgroundTasks):
    if payload.purpose not in ALLOWED_PURPOSES:
        raise HTTPException(status_code=400, detail="Недопустимая цель кредита")
    if not payload.bkiConsent:
        raise HTTPException(status_code=400, detail="Требуется согласие на запрос в БКИ")
    if payload.purpose not in ALLOWED_PURPOSES:
        raise HTTPException(status_code=400, detail="Недопустимая цель кредита")
    if payload.termMonths not in ALLOWED_TERM_MONTHS:
        raise HTTPException(status_code=400, detail="Недопустимый срок кредита")
    if not payload.bkiConsent:
        raise HTTPException(status_code=400, detail="Требуется согласие на запрос в БКИ")

    phone = _normalize_phone(payload.phoneNumber)

    with SessionLocal() as db:
        existing = db.execute(
            select(models.User).where(models.User.phone_number == phone)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=400, detail="Телефон уже зарегистрирован")

        user = models.User(
            id=str(uuid.uuid4()),
            phone_number=phone,
            inn=payload.inn,
            is_admin=False,
            company_name=payload.companyName,
        )
        db.add(user)
        db.flush()

        application = models.Application(
            client_id=user.id,
            number=1,
            status="PRESCORING",
            credit_sum=payload.creditSum,
            has_collateral=payload.hasCollateral,
            purpose=payload.purpose,
            requested_term_months=payload.termMonths, 
            revenue_last_12m=payload.revenueLast12m,
            bki_consent=payload.bkiConsent,
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

        client_id = user.id
        application_id = str(application.id)

    store = get_session_store()
    token = create_session(store, client_id, config.settings.COOKIE_MAX_AGE)
    response = JSONResponse(
        content={
            "clientId": client_id,
            "applicationId": application_id,
            "isAdmin": False,
        },
        status_code=201,
    )
    _set_auth_cookie(response, token)
    background.add_task(run_scoring, application_id)
    return response


@router.post("/login")
def login(payload: LoginRequest):
    phone = _normalize_phone(payload.phoneNumber)

    with SessionLocal() as db:
        user = db.execute(
            select(models.User).where(models.User.phone_number == phone)
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="Неверный номер телефона")
        client_id = user.id
        is_admin = bool(user.is_admin)

    store = get_session_store()
    token = create_session(store, client_id, config.settings.COOKIE_MAX_AGE)
    response = JSONResponse(
        content={"clientId": client_id, "isAdmin": is_admin},
        status_code=200,
    )
    _set_auth_cookie(response, token)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(config.settings.COOKIE_NAME)
    if token:
        get_session_store().delete(token)
    response = Response(status_code=204)
    response.delete_cookie(config.settings.COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=UserResponse)
def me(user: models.User = Depends(get_current_user)):
    return UserResponse(
        clientId=user.id,
        phoneNumber=user.phone_number,
        inn=user.inn,
        isAdmin=bool(user.is_admin),
        createdAt=user.created_at,
    )