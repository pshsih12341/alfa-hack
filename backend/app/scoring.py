"""Имитация прескоринга до подключения ML.

Детерминированно: SUCCESS если creditSum <= limit_max продукта, иначе REJECTED.
Никакого random — жюри должно получать одинаковый ответ на одинаковый запрос.

Когда ML-сервис будет готов, тело run_scoring заменится на HTTP-вызов /score
(SCORING_MODE=ml), интерфейс (application_id -> обновление статуса) сохранится.
"""

import time

from sqlalchemy import select

from . import models
from .database import SessionLocal

SCORING_DELAY_SECONDS = 5


def run_scoring(application_id: str) -> None:
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