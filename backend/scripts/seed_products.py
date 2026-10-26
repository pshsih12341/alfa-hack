"""Идемпотентный seed продуктов для кредитного кабинета.

По коду (code) либо вставляет, либо обновляет запись в products.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Product  # noqa: E402


COMMON_PURPOSES = [
    "Покупка недвижимости",
    "Покупка имущества",
    "Покупка оборудования",
    "Ремонт",
    "Текущие расходы",
    "Пополнение оборотных средств",
    "Рефинансирование",
]


def _load_products() -> list[Product]:
    # ML выбирает продукт по hasCollateral (no_collateral или collateral), оба должны быть в БД.
    # Лимиты — как в ML (ml/config/scoring.yaml); rate — минимальная ставка продукта,
    # фактическую ставку заявки даёт ML.
    return [
        Product(
            code="no_collateral",
            product_name="Кредит для бизнеса без залога",
            purpose=COMMON_PURPOSES,
            rate=18,
            limit_min=100_000, limit_max=30_000_000,
            term_min=6, term_max=36, term_step=6,
            business_type="LLC", with_collateral=False,
        ),
        Product(
            code="collateral",
            product_name="Кредит для бизнеса под залог",
            purpose=COMMON_PURPOSES,
            rate=17.5,
            limit_min=100_000, limit_max=30_000_000,
            term_min=6, term_max=36, term_step=6,
            business_type="LLC", with_collateral=True,
        ),
    ]


def main() -> None:
    with SessionLocal() as db:
        for product in _load_products():
            existing = db.query(Product).filter(Product.code == product.code).first()
            if existing:
                for key, value in product.__dict__.items():
                    if key in ("id", "_sa_instance_state"):
                        continue
                    setattr(existing, key, value)
                db.commit()
                print(f"Обновлён товар: {product.code}")
            else:
                db.add(product)
                db.commit()
                print(f"Добавлен товар: {product.code}")


if __name__ == "__main__":
    main()