from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from uuid import uuid4

from .. import auth, config, models, schemas
from ..database import SessionLocal

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/reg", response_model=schemas.RegisterResponse)
def register(payload: schemas.RegisterRequest, request: Request):
    phone = schemas.normalize_phone_number(payload.phoneNumber)
    with SessionLocal() as db:
        existing = db.execute(
            select(models.User).where(models.User.phone_number == phone)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=400, detail="Телефон уже зарегистрирован")
        user = models.User(
            id=str(uuid4()),
            phone_number=phone,
            credit_sum=payload.creditSum,
            purpose=payload.purpose,
            income=payload.income,
            inn=payload.inn,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    token = auth.create_session(auth.get_session_store(), user.id, config.settings.COOKIE_MAX_AGE)
    response = JSONResponse(content={"clientId": user.id}, status_code=201)
    auth._set_auth_cookie(response, token)
    return response


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, request: Request):
    phone = schemas.normalize_phone_number(payload.phoneNumber)
    with SessionLocal() as db:
        user = db.execute(
            select(models.User).where(models.User.phone_number == phone)
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="Неверный номер телефона")
        token = auth.create_session(auth.get_session_store(), user.id, config.settings.COOKIE_MAX_AGE)
    response = JSONResponse(
        content={"clientId": user.id, "isAdmin": bool(user.is_admin)}
    )
    auth._set_auth_cookie(response, token)
    return response


@router.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return schemas.UserResponse(
        clientId=current_user.id,
        phoneNumber=current_user.phone_number,
        creditSum=current_user.credit_sum,
        purpose=current_user.purpose,
        income=current_user.income,
        inn=current_user.inn,
        isAdmin=current_user.is_admin,
        createdAt=current_user.created_at,
    )
