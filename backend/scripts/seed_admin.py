#!/usr/bin/env python3
"""Скрипт: ручное создание администратора в БД.

Использование:
    python3 scripts/seed_admin.py +790****0000
Если номер не задан, берётся +790****0000.
"""
import os
import sys
from datetime import datetime
from uuid import uuid4

# путь к корню проекта, чтобы импортировать backend.app.*
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.models import User

DEFAULT_ADMIN_PHONE = "+790****0000"


def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADMIN_PHONE
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.phone_number == phone)
        ).scalar_one_or_none()
        if existing:
            print(f"Админ уже есть: {phone} (id={existing.id}, is_admin={existing.is_admin})")
            return
        admin = User(
            id=str(uuid4()),
            phone_number=phone,
            credit_sum=0,
            purpose="",
            income=0,
            inn="",
            is_admin=True,
            created_at=datetime.now(),
        )
        db.add(admin)
        db.commit()
        print(f"Админ создан: id={admin.id}, phone={admin.phone_number}, is_admin=True")
    finally:
        db.close()


if __name__ == "__main__":
    main()
