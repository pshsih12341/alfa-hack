"""Создает готовых демо-клиентов для защиты. Очищает старые тестовые данные."""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal, utcnow
from app.models import User, Application, ApplicationStatusHistory, Session as DBSession

DEMO_USERS = [
    # Формат: (Телефон, ИНН, Сумма, Срок, Имя, Статус, Залог)
    ("+79991112233", "7476595370", 2450000, 24, "ООО Ромашка Строй", "SUCCESS", False),
    ("+79992223344", "5483374635", 4100000, 12, "ООО Альтаир Трейд", "OFFER", False),
    ("+79993334455", "669985868171", 500000, 24, "ИП Волкова В.И.", "REJECTED", False),
    ("+79994445566", "5991587272", 1050000, 18, "ООО Ресурс Строй", "INFO", False),
    ("+79995556677", "7476595370", 2450000, 24, "ООО Ромашка Строй (Залог)", "SUCCESS", True), # Для теста залога
]

def main():
    with SessionLocal() as db:
        print("Очистка старых заявок...")
        db.query(ApplicationStatusHistory).delete()
        db.query(Application).delete()
        db.query(DBSession).delete()
        # Удаляем клиентов, но НЕ трогаем админа
        db.query(User).filter(User.is_admin == False).delete()
        db.commit()

        print("Создание демо-аккаунтов...")
        for phone, inn, amount, term, name, status, has_collateral in DEMO_USERS:
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
                id=str(uuid.uuid4()),
                client_id=user.id,
                number=1,
                status=status,
                credit_sum=amount,
                purpose="equipment",
                requested_term_months=term,
                has_collateral=has_collateral,
                bki_consent=True,
                bki_consent_at=utcnow(),
            )
            db.add(app)
            db.flush()
            db.add(ApplicationStatusHistory(application_id=app.id, status=status))
            db.commit()
            print(f"  {phone} | {inn} | {name} -> {status} (залог: {has_collateral})")

if __name__ == "__main__":
    main()