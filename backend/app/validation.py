"""Проверки заявки до скоринга — те же правила, что в ML-сервисе.

Ошибку здесь клиент видит сразу в форме (400), а не отказом после скоринга.
"""

from fastapi import HTTPException

from .schemas import ALLOWED_PURPOSES, ALLOWED_TERM_MONTHS, CREDIT_SUM_MAX, CREDIT_SUM_MIN

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _check_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def is_valid_inn(inn: str) -> bool:
    """10 цифр — организация, 12 — ИП; контрольные цифры должны сойтись."""
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = [int(c) for c in inn]
    if len(inn) == 10:
        return _check_digit(digits[:9], _W10) == digits[9]
    return _check_digit(digits[:10], _W11) == digits[10] and _check_digit(digits[:11], _W12) == digits[11]


def _rub(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def validate_application(credit_sum: int, purpose: str, term_months: int, refinance_loan_ids: list[int]) -> None:
    if purpose not in ALLOWED_PURPOSES:
        raise HTTPException(status_code=400, detail="Недопустимая цель кредита")
    if term_months not in ALLOWED_TERM_MONTHS:
        raise HTTPException(status_code=400, detail="Недопустимый срок кредита")
    if not CREDIT_SUM_MIN <= credit_sum <= CREDIT_SUM_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Сумма кредита — от {_rub(CREDIT_SUM_MIN)} до {_rub(CREDIT_SUM_MAX)} ₽",
        )
    if refinance_loan_ids and purpose != "refinancing":
        raise HTTPException(status_code=400, detail="Кредиты к рефинансированию выбираются только для цели «Рефинансирование»")
