"""Идентификаторы: уникальные ИНН с корректными контрольными цифрами, сквозные номера, названия."""
import numpy as np

from alfa_ml.inn import W10, W11, W12, check_digit, ogrn_check_digit

REGIONS = np.array([2, 16, 23, 24, 36, 50, 52, 54, 59, 61, 63, 66, 74, 77, 78])

COMPANY_WORDS = ["Вектор", "Ромашка", "Альтаир", "Север", "Гранит", "Меридиан", "Орион", "Полюс", "Сфера",
                 "Импульс", "Каскад", "Ресурс", "Триада", "Квант", "Атлант", "Восход", "Горизонт", "Профиль"]
COMPANY_SUFFIXES = ["", " Плюс", " Групп", " Трейд", " Сервис", " Строй", " Логистик"]
# Пары форм фамилии: в данных хранится только строка с ФИО, пол не хранится.
SURNAMES = [("Иванов", "Иванова"), ("Петров", "Петрова"), ("Смирнов", "Смирнова"), ("Кузнецов", "Кузнецова"),
            ("Соколов", "Соколова"), ("Попов", "Попова"), ("Лебедев", "Лебедева"), ("Козлов", "Козлова"),
            ("Новиков", "Новикова"), ("Морозов", "Морозова"), ("Волков", "Волкова"), ("Зайцев", "Зайцева")]
INITIALS = list("АБВГДЕИКЛМНОПРСТ")


class IdCounter:
    """Сквозная нумерация по всем выборкам."""

    def __init__(self, start: int = 1):
        self._next = start

    def take(self, n: int) -> np.ndarray:
        ids = np.arange(self._next, self._next + n, dtype=np.int64)
        self._next += n
        return ids


class InnFactory:
    """Выдаёт ИНН без повторов во всех выборках."""

    def __init__(self, rng: np.random.Generator):
        self._rng = rng
        self._used = {9: np.empty(0, np.int64), 10: np.empty(0, np.int64)}
        self._ogrn_used: set[str] = set()

    def _bodies(self, n: int, width: int) -> np.ndarray:
        """Номера без контрольных цифр: код региона и случайная часть."""
        result = np.empty(0, np.int64)
        while result.size < n:
            need = n - result.size
            region = self._rng.choice(REGIONS, size=need).astype(np.int64)
            serial = self._rng.integers(0, 10 ** (width - 2), size=need, dtype=np.int64)
            fresh = np.unique(region * 10 ** (width - 2) + serial)
            fresh = fresh[~np.isin(fresh, self._used[width]) & ~np.isin(fresh, result)]
            result = np.concatenate([result, fresh])
        result = self._rng.permutation(result[:n])
        self._used[width] = np.concatenate([self._used[width], result])
        return result

    def companies(self, n: int) -> np.ndarray:
        """ИНН организаций: 10 цифр."""
        bodies = self._bodies(n, 9)
        check = check_digit(_digits(bodies, 9), W10)
        return np.array([f"{body:09d}{c}" for body, c in zip(bodies, check)], dtype=object)

    def persons(self, n: int) -> np.ndarray:
        """ИНН физлиц и ИП: 12 цифр."""
        bodies = self._bodies(n, 10)
        digits = _digits(bodies, 10)
        c11 = check_digit(digits, W11)
        c12 = check_digit(np.column_stack([digits, c11]), W12)
        return np.array([f"{body:010d}{a}{b}" for body, a, b in zip(bodies, c11, c12)], dtype=object)

    def ogrn(self, inn: np.ndarray, registration_year: np.ndarray, ip: np.ndarray) -> np.ndarray:
        """ОГРН (ООО, 13 цифр) или ОГРНИП (ИП, 15 цифр): признак, год, регион из ИНН, номер, контрольная цифра."""
        result = np.empty(inn.size, dtype=object)
        for i, (code, year, is_ip) in enumerate(zip(inn, registration_year, ip)):
            serial_digits = 9 if is_ip else 7
            while True:
                serial = int(self._rng.integers(0, 10 ** serial_digits))
                body = f"{3 if is_ip else 1}{year % 100:02d}{code[:2]}{serial:0{serial_digits}d}"
                if body not in self._ogrn_used:
                    self._ogrn_used.add(body)
                    break
            length = len(body) + 1
            result[i] = f"{body}{ogrn_check_digit(int(body), length)}"
        return result


def _digits(numbers: np.ndarray, width: int) -> np.ndarray:
    powers = 10 ** np.arange(width - 1, -1, -1, dtype=np.int64)
    return numbers[:, None] // powers % 10


def company_names(rng: np.random.Generator, n: int) -> np.ndarray:
    words = rng.choice(COMPANY_WORDS, size=n)
    suffixes = rng.choice(COMPANY_SUFFIXES, size=n)
    return np.array([f"ООО «{w}{s}»" for w, s in zip(words, suffixes)], dtype=object)


def person_names(rng: np.random.Generator, n: int) -> np.ndarray:
    pairs = rng.integers(0, len(SURNAMES), size=n)
    forms = rng.integers(0, 2, size=n)
    first = rng.choice(INITIALS, size=n)
    middle = rng.choice(INITIALS, size=n)
    return np.array([f"{SURNAMES[p][f]} {a}. {b}." for p, f, a, b in zip(pairs, forms, first, middle)], dtype=object)
