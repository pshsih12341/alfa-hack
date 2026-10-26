"""Создает готовых демо-клиентов для защиты. Очищает старые тестовые данные.

Заявки создаются в PRESCORING и проходят настоящий скоринг (run_scoring): статусы,
варианты и ставки — из ML, как у заявок из формы. Запуск, когда ML-сервис поднят:
docker compose exec backend python scripts/seed_demo.py
"""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal, utcnow
from app.models import Application, ApplicationStatusHistory, PaymentOrder, Session as DBSession, User
from app.scoring import run_scoring

DEMO_USERS = [
    # (Телефон, ИНН, Сумма, Срок, Имя, Цель, Залог) → ожидаемое решение
    ("+79991112233", "7476595370", 2_450_000, 24, "ООО «Ромашка Строй»", "working_capital", False),  # SUCCESS, 18%
    ("+79995556677", "7476595370", 2_450_000, 24, "ООО «Ромашка Строй» (залог)", "working_capital", True),  # SUCCESS, 17,5%
    ("+79992223344", "5483374635", 4_100_000, 12, "ООО «Альтаир Трейд»", "working_capital", False),  # OFFER
    ("+79993334455", "669985868171", 500_000, 24, "ИП Волкова В. И.", "working_capital", False),  # REJECTED
    ("+79994445566", "5991587272", 1_050_000, 18, "ООО «Ресурс Строй»", "working_capital", False),  # INFO: файлы 1С
    ("+79996667788", "524267417656", 300_000, 12, "ИП Соколов Р. М.", "working_capital", False),  # INFO: счёт в Альфе
]


def main():
    with SessionLocal() as db:
        print("Очистка старых заявок...")
        db.query(PaymentOrder).delete()
        db.query(ApplicationStatusHistory).delete()
        db.query(Application).delete()
        db.query(DBSession).delete()
        # Удаляем клиентов, но НЕ трогаем админа
        db.query(User).filter(User.is_admin == False).delete()  # noqa: E712
        db.commit()

        print("Создание демо-аккаунтов...")
        created = []
        for phone, inn, amount, term, name, purpose, has_collateral in DEMO_USERS:
            user = User(
                id=str(uuid.uuid4()),
                phone_number=phone,
                inn=inn,
                is_admin=False,
                company_name=name,
            )
            db.add(user)
            db.flush()

            app = Application(
                client_id=user.id,
                number=1,
                status="PRESCORING",
                credit_sum=amount,
                purpose=purpose,
                requested_term_months=term,
                has_collateral=has_collateral,
                bki_consent=True,
                bki_consent_at=utcnow(),
                refinance_loan_ids=[],
            )
            db.add(app)
            db.flush()
            db.add(ApplicationStatusHistory(application_id=app.id, status="PRESCORING"))
            created.append((phone, inn, name, has_collateral, app.id))
        db.commit()

    print("Скоринг...")
    for phone, inn, name, has_collateral, application_id in created:
        outcome = run_scoring(str(application_id))
        with SessionLocal() as db:
            status = db.get(Application, application_id).status
        suffix = "" if outcome == "done" else " (ML не ответил — заявка дождётся повторного скоринга)"
        print(f"  {phone} | {inn} | {name} -> {status} (залог: {has_collateral}){suffix}")


if __name__ == "__main__":
    main()
