"""Создать админа по номеру телефона."""

import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def normalize(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


def main() -> None:
    phone = sys.argv[1] if len(sys.argv) > 1 else "+79000000000"
    phone = normalize(phone)

    with SessionLocal() as db:
        existing = db.query(User).filter(User.phone_number == phone).first()
        if existing is not None:
            existing.is_admin = True
            db.commit()
            print(f"Пользователь {phone} уже существует — сделан админом")
            return
        user = User(
            id=str(uuid.uuid4()),
            phone_number=phone,
            inn="",
            is_admin=True,
            company_name="Администратор",
        )
        db.add(user)
        db.commit()
        print(f"Создан админ {phone} (id={user.id})")


if __name__ == "__main__":
    main()