"""ИНН и ОГРН: контрольные цифры и проверка."""
import numpy as np

W10 = np.array([2, 4, 10, 3, 5, 9, 4, 6, 8])
W11 = np.array([7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
W12 = np.array([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])


def check_digit(digits: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Контрольная цифра: взвешенная сумма цифр по модулю 11, затем по модулю 10."""
    return digits @ weights % 11 % 10


def is_valid_inn(inn: str) -> bool:
    """10 цифр — организация, 12 — физлицо или ИП; контрольные цифры должны сойтись."""
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = np.array([int(c) for c in inn])
    if len(inn) == 10:
        return bool(check_digit(digits[:9], W10) == digits[9])
    return bool(check_digit(digits[:10], W11) == digits[10] and check_digit(digits[:11], W12) == digits[11])


def ogrn_check_digit(body: int, length: int) -> int:
    """Контрольная цифра ОГРН (13 цифр: остаток от деления на 11) или ОГРНИП (15 цифр: на 13)."""
    return body % (11 if length == 13 else 13) % 10


def is_valid_ogrn(ogrn: str) -> bool:
    """13 цифр — ОГРН организации, 15 — ОГРНИП."""
    if not ogrn.isdigit() or len(ogrn) not in (13, 15):
        return False
    return ogrn_check_digit(int(ogrn[:-1]), len(ogrn)) == int(ogrn[-1])
