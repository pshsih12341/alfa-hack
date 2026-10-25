"""Формат 1CClientBankExchange — выгрузка выписки из клиент-банка для 1С: разбор и запись.

Файл: шапка «ключ=значение», секция СекцияРасчСчет…КонецРасчСчет с периодом и остатками,
затем документы СекцияДокумент=…КонецДокумента, в конце КонецФайла. Кодировка — Windows-1251
(«Кодировка=Windows»), реже UTF-8 или DOS (CP866).
"""
import datetime as dt
from dataclasses import dataclass

import pandas as pd

DOCUMENT_FIELDS = {
    "Номер": "number", "Дата": "date", "Сумма": "amount",
    "ПлательщикСчет": "payer_account", "ПлательщикИНН": "payer_inn", "Плательщик1": "payer_name",
    "ПолучательСчет": "receiver_account", "ПолучательИНН": "receiver_inn", "Получатель1": "receiver_name",
    "ДатаСписано": "date_debited", "ДатаПоступило": "date_credited",
    "НазначениеПлатежа": "purpose", "ПоказательКБК": "kbk", "ВидОплаты": "payment_kind",
}


class StatementFormatError(ValueError):
    """Файл не похож на выгрузку 1CClientBankExchange."""


@dataclass
class Statement:
    account: str  # расчётный счёт, по которому выписка
    period_start: dt.date | None
    period_end: dt.date | None
    documents: pd.DataFrame  # колонки — значения DOCUMENT_FIELDS, плюс doc_type


def decode(raw: bytes) -> str:
    """Текст файла: UTF-8, иначе Windows-1251; если в шапке «Кодировка=DOS» — CP866."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    if "Кодировка=DOS" in text[:500]:
        text = raw.decode("cp866")
    return text


def _date(value: str | None) -> dt.date | None:
    return dt.datetime.strptime(value.strip(), "%d.%m.%Y").date() if value and value.strip() else None


def parse(raw: bytes) -> Statement:
    lines = [line.strip() for line in decode(raw).splitlines()]
    if not lines or lines[0] != "1CClientBankExchange":
        raise StatementFormatError("Нет заголовка 1CClientBankExchange — это не выгрузка для 1С")
    header, documents, current = {}, [], None
    for line in lines[1:]:
        if line.startswith("СекцияДокумент="):
            current = {"doc_type": line.split("=", 1)[1]}
        elif line == "КонецДокумента":
            if current is not None:
                documents.append(current)
            current = None
        elif "=" in line:
            key, value = line.split("=", 1)
            if current is not None:
                if key in DOCUMENT_FIELDS:
                    current[DOCUMENT_FIELDS[key]] = value.strip()
            elif key not in header:
                header[key] = value.strip()
    account = header.get("РасчСчет", "")
    if not account:
        raise StatementFormatError("В шапке нет расчётного счёта (РасчСчет)")
    frame = pd.DataFrame(documents, columns=["doc_type", *DOCUMENT_FIELDS.values()], dtype=object).fillna("")
    try:
        frame["amount"] = frame["amount"].str.replace(",", ".").str.replace(" ", "").astype(float)
        for col in ("date", "date_debited", "date_credited"):
            frame[col] = pd.to_datetime(frame[col].where(frame[col] != ""), format="%d.%m.%Y", errors="raise")
    except (ValueError, TypeError) as error:
        raise StatementFormatError(f"Не удалось прочитать сумму или дату документа: {error}") from error
    return Statement(account, _date(header.get("ДатаНачала")), _date(header.get("ДатаКонца")), frame)


def write(account: str, period_start: dt.date, period_end: dt.date, documents: list[dict],
          created: dt.date) -> bytes:
    """Файл выгрузки в Windows-1251. documents — словари с ключами DOCUMENT_FIELDS (значения-строки)."""
    def date(value: dt.date) -> str:
        return value.strftime("%d.%m.%Y")

    inflow = sum(d["amount"] for d in documents if d["receiver_account"] == account)
    outflow = sum(d["amount"] for d in documents if d["payer_account"] == account)
    lines = [
        "1CClientBankExchange", "ВерсияФормата=1.03", "Кодировка=Windows", "Отправитель=Клиент-банк", "Получатель=",
        f"ДатаСоздания={date(created)}", "ВремяСоздания=10:00:00",
        f"ДатаНачала={date(period_start)}", f"ДатаКонца={date(period_end)}", f"РасчСчет={account}",
        "СекцияРасчСчет", f"ДатаНачала={date(period_start)}", f"ДатаКонца={date(period_end)}", f"РасчСчет={account}",
        "НачальныйОстаток=0.00", f"ВсегоПоступило={inflow:.2f}", f"ВсегоСписано={outflow:.2f}",
        f"КонечныйОстаток={inflow - outflow:.2f}", "КонецРасчСчет",
    ]
    by_name = {v: k for k, v in DOCUMENT_FIELDS.items()}
    for doc in documents:
        lines.append("СекцияДокумент=Платежное поручение")
        for field in DOCUMENT_FIELDS.values():
            value = doc.get(field)
            if value is None or value == "":
                continue
            if field == "amount":
                value = f"{value:.2f}"
            elif isinstance(value, dt.date):
                value = date(value)
            lines.append(f"{by_name[field]}={value}")
        lines.append("КонецДокумента")
    lines.append("КонецФайла")
    return "\r\n".join(lines).encode("cp1251")
