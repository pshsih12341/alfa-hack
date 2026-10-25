"""Скоринг заявки: mock или ml.

- SCORING_MODE=mock — детерминированная заглушка (SUCCESS/REJECTED по лимиту
  продукта).
- SCORING_MODE=ml — HTTP POST в ML-сервис /score:
  - таймаут, ошибка соединения или 5xx — ещё две попытки с паузой. Если ML так и
    не ответил, заявка остаётся в PRESCORING (без автоотказа), и её подхватит
    повторный скоринг rescore_stuck;
  - 404 (ИНН нет в реестре) и 422 (данные не прошли проверку) — на этапе 1 заявка
    отклоняется с понятным clientMessage, на этапе 2 возвращается в прежний статус
    (INFO или OFFER): клиент может загрузить другие выписки.
"""

import logging
import time
from datetime import timedelta

import httpx
from sqlalchemy import select

from . import models
from .config import settings
from .database import SessionLocal, utcnow

logger = logging.getLogger(__name__)

SCORING_DELAY_SECONDS = 5
RETRY_DELAYS_SECONDS = (2, 5)  # паузы перед повторами, если ML не ответил
STUCK_AFTER_SECONDS = 60  # с этого возраста заявку в PRESCORING скорит rescore_stuck

# Соответствие decision из ML → status в нашей БД
ML_DECISION_TO_STATUS = {
    "APPROVED": "SUCCESS",
    "OFFER": "OFFER",
    "INFO": "INFO",
    "REJECTED": "REJECTED",
}


def run_scoring(application_id: str, retry: bool = True) -> str:
    """Скоринг заявки в PRESCORING. Итог: done, unavailable (ML не ответил) или skipped."""
    if settings.SCORING_MODE == "ml":
        return _run_scoring_ml(application_id, retry)
    _run_scoring_mock(application_id)
    return "done"


def rescore_stuck() -> int:
    """Повторный скоринг заявок, застрявших в PRESCORING, пока ML был недоступен.

    Пока ML не отвечает, обход прерывается на первой же заявке. Возвращает число
    заявок, получивших решение.
    """
    cutoff = (utcnow() - timedelta(seconds=STUCK_AFTER_SECONDS)).replace(tzinfo=None)
    with SessionLocal() as db:
        ids = (
            db.execute(
                select(models.Application.id)
                .where(models.Application.status == "PRESCORING")
                .where(models.Application.updated_at < cutoff)
                .order_by(models.Application.created_at.asc())
            )
            .scalars()
            .all()
        )
    scored = 0
    for application_id in ids:
        outcome = run_scoring(str(application_id), retry=False)
        if outcome == "unavailable":
            break
        scored += outcome == "done"
    return scored


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

def _run_scoring_ml(application_id: str, retry: bool) -> str:
    # читаем заявку, формируем payload
    with SessionLocal() as db:
        application = db.get(models.Application, application_id)
        if application is None or application.status != "PRESCORING":
            return "skipped"

        payload = {
            "applicationId": str(application.id),
            "inn": _get_client_inn(application.client_id, db),
            "creditSum": application.credit_sum,
            "termMonths": application.requested_term_months,
            "purpose": application.purpose,
            "refinanceLoanIds": application.refinance_loan_ids or [],
            "revenueLast12m": application.revenue_last_12m,
            "bkiConsent": bool(application.bki_consent),
            "hasCollateral": bool(application.has_collateral),
            "useAlfaAccount": False,
            "statements": None,
        }
        # Этап 2: клиент разрешил взять обороты по счёту в Альфе и/или загрузил выписки.
        info = application.additional_info or {}
        if info.get("useAlfaAccount"):
            payload["useAlfaAccount"] = True
        if info.get("statements"):
            payload["statements"] = info["statements"]
    stage2 = payload["useAlfaAccount"] or bool(payload["statements"])

    outcome, data = _call_ml(payload, RETRY_DELAYS_SECONDS if retry else ())
    if outcome == "unavailable":
        logger.warning(
            "ML /score недоступен для заявки %s (%s) — оставляем в PRESCORING, повторим позже",
            application_id,
            data["detail"],
        )
        return "unavailable"

    # применяем результат
    with SessionLocal() as db:
        application = db.get(models.Application, application_id)
        if application is None or application.status != "PRESCORING":
            return "skipped"

        if outcome == "invalid":
            new_status = _apply_error(application, data, stage2)
        else:
            new_status = _apply_decision(application, data, db)
            if new_status is None:
                logger.warning(
                    "ML /score unknown decision=%r for application %s — пропускаем",
                    data.get("decision"),
                    application_id,
                )
                return "skipped"

        db.add(
            models.ApplicationStatusHistory(
                application_id=application.id, status=new_status
            )
        )
        db.commit()
        logger.info(
            "ML /score application=%s outcome=%s status=%s",
            application_id,
            outcome,
            new_status,
        )
    return "done"


def _call_ml(payload: dict, retry_delays: tuple[int, ...]) -> tuple[str, dict]:
    """("ok", ответ ML) | ("invalid", {"status", "detail"}) | ("unavailable", {"detail"})."""
    problem = ""
    for delay in (0, *retry_delays):
        time.sleep(delay)
        try:
            response = httpx.post(
                f"{settings.SCORING_URL}/score",
                json=payload,
                timeout=settings.SCORING_TIMEOUT_SECONDS,
            )
        except httpx.TransportError as exc:  # таймаут, нет соединения
            problem = repr(exc)
            continue
        if response.status_code in (404, 422):
            return "invalid", {"status": response.status_code, "detail": _error_detail(response)}
        if response.status_code >= 400:
            problem = f"HTTP {response.status_code}"
            continue
        try:
            return "ok", response.json()
        except ValueError:
            problem = "ответ не JSON"
    return "unavailable", {"detail": problem}


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text[:300]
    if isinstance(detail, list):  # ошибки валидации полей запроса
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail)


def _apply_decision(application: models.Application, data: dict, db) -> str | None:
    new_status = ML_DECISION_TO_STATUS.get(data.get("decision"))
    if new_status is None:
        return None
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
    return new_status


def _apply_error(application: models.Application, error: dict, stage2: bool) -> str:
    """Данные заявки не прошли проверку ML (404 или 422)."""
    if stage2:
        # Возвращаем решение этапа 1: клиент может загрузить другие выписки.
        previous = dict(application.scoring_response or {})
        previous["clientMessage"] = (
            f"Не удалось проверить выписки: {error['detail']}. "
            "Загрузите выписки по расчётным счетам вашей компании ещё раз."
        )
        previous["lastError"] = error
        application.scoring_response = previous
        application.status = ML_DECISION_TO_STATUS.get(previous.get("decision"), "INFO")
        return application.status

    application.status = "REJECTED"
    application.scoring_response = {
        "decision": "REJECTED",
        "clientMessage": _error_message(error),
        "error": error,
    }
    return application.status


def _error_message(error: dict) -> str:
    if error["status"] == 404:
        return "Не нашли организацию с этим ИНН в ЕГРЮЛ и ЕГРИП. Проверьте ИНН и подайте заявку снова."
    if "revenueLast12m" in error["detail"]:
        return (
            "Не нашли выручку вашего бизнеса в источниках. "
            "Подайте заявку снова и укажите выручку за последние 12 месяцев."
        )
    return f"Не удалось рассмотреть заявку: {error['detail']}. Исправьте данные и подайте заявку снова."


def _get_client_inn(client_id: str, db) -> str:
    user = db.get(models.User, client_id)
    return user.inn if user else ""
