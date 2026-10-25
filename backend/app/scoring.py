"""Скоринг заявки: mock или ml.

- SCORING_MODE=mock — детерминированная заглушка (SUCCESS/REJECTED по лимиту
  продукта). Используется по умолчанию и на защите, если ML не готов.
- SCORING_MODE=ml — HTTP POST в ML-сервис /score. При таймауте/ошибке заявка
  остаётся в PRESCORING (без автоотказа), событие пишется в лог.
"""

import logging
import time

import httpx
from sqlalchemy import select

from . import models
from .config import settings
from .database import SessionLocal

logger = logging.getLogger(__name__)

SCORING_DELAY_SECONDS = 5

# Соответствие decision из ML → status в нашей БД
ML_DECISION_TO_STATUS = {
    "APPROVED": "SUCCESS",
    "OFFER": "OFFER",
    "INFO": "INFO",
    "REJECTED": "REJECTED",
}


def run_scoring(application_id: str) -> None:
    if settings.SCORING_MODE == "ml":
        _run_scoring_ml(application_id)
    else:
        _run_scoring_mock(application_id)


# ---------- mock ----------

def _run_scoring_mock(application_id: str) -> None:
    time.sleep(SCORING_DELAY_SECONDS)

    with SessionLocal() as db:
        application = db.get(models.Application, application_id)
        if application is None or application.status != "PRESCORING":
            return

        no_col = db.execute(
            select(models.Product).where(models.Product.code == "no_collateral")
        ).scalar_one_or_none()

        if no_col is None or application.credit_sum > no_col.limit_max:
            new_status = "REJECTED"
            product_id = None
        else:
            new_status = "SUCCESS"
            product_id = no_col.id

        application.status = new_status
        if product_id is not None:
            application.product_id = product_id
        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status=new_status
            )
        )
        db.commit()


# ---------- ml ----------

def _run_scoring_ml(application_id: str) -> None:
    # читаем заявку, формируем payload
    with SessionLocal() as db:
        application = db.get(models.Application, application_id)
        if application is None or application.status != "PRESCORING":
            return

        payload = {
            "applicationId": str(application.id),
            "inn": _get_client_inn(application.client_id, db),
            "creditSum": application.credit_sum,
            "termMonths": application.requested_term_months,
            "purpose": application.purpose,
            "refinanceLoanIds": application.refinance_loan_ids or [],
            "revenueLast12m": application.revenue_last_12m,
            "bkiConsent": bool(application.bki_consent),
            "useAlfaAccount": False,
            "statements": None,
        }

    # вызываем ML
    try:
        response = httpx.post(
            f"{settings.SCORING_URL}/score",
            json=payload,
            timeout=settings.SCORING_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        logger.warning(
            "ML /score timeout for application %s — оставляем в PRESCORING",
            application_id,
        )
        return
    except httpx.HTTPError as exc:
        logger.warning(
            "ML /score failed for application %s: %s — оставляем в PRESCORING",
            application_id,
            exc,
        )
        return
    except ValueError:
        logger.warning(
            "ML /score returned non-JSON for application %s — оставляем в PRESCORING",
            application_id,
        )
        return

    decision = data.get("decision")
    new_status = ML_DECISION_TO_STATUS.get(decision)
    if new_status is None:
        logger.warning(
            "ML /score unknown decision=%r for application %s — пропускаем",
            decision,
            application_id,
        )
        return

    # применяем результат
    with SessionLocal() as db:
        application = db.get(models.Application, application_id)
        if application is None:
            return
        if application.status != "PRESCORING":
            return

        application.status = new_status
        application.scoring_response = data

        # для SUCCESS — выбрать продукт
        if new_status == "SUCCESS":
            product_code = data.get("product") or "no_collateral"
            product = db.execute(
                select(models.Product).where(models.Product.code == product_code)
            ).scalar_one_or_none()
            if product is not None:
                application.product_id = product.id
            if data.get("rate"):
                application.rate = float(data["rate"])

        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status=new_status
            )
        )
        db.commit()
        logger.info(
            "ML /score application=%s decision=%s status=%s",
            application_id,
            decision,
            new_status,
        )


def _get_client_inn(client_id: str, db) -> str:
    user = db.get(models.User, client_id)
    return user.inn if user else ""