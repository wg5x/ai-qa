from datetime import date
from decimal import Decimal
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ContractRecord, QuoteRecord


NO_RECORDS_MESSAGE = "未找到历史价格记录"
FOUND_RECORDS_MESSAGE = "找到历史价格记录"
INVALID_QUERY_MESSAGE = "请输入客户名称和型号"
REPLACEMENT_NUMBER_SEPARATOR = re.compile(r"[,;，；、/\s]+")


def search_historical_prices(
    db: Session, customer_name: str, part_number: str
) -> dict[str, object]:
    customer_query = customer_name.strip()
    part_query = part_number.strip()
    if not customer_query or not part_query:
        return _empty_result(INVALID_QUERY_MESSAGE)

    quotes = _find_exact_quotes(db, customer_query, part_query)
    contracts = _find_contracts(db, customer_query, part_query)

    if not quotes and not contracts:
        quotes = _find_replacement_quotes(db, customer_query, part_query)

    serialized_quotes = [_serialize_quote(record) for record in quotes]
    serialized_contracts = [_serialize_contract(record) for record in contracts]
    found = bool(serialized_quotes or serialized_contracts)

    return {
        "found": found,
        "message": FOUND_RECORDS_MESSAGE if found else NO_RECORDS_MESSAGE,
        "quotes": serialized_quotes,
        "contracts": serialized_contracts,
    }


def _empty_result(message: str) -> dict[str, object]:
    return {"found": False, "message": message, "quotes": [], "contracts": []}


def _find_exact_quotes(
    db: Session, customer_name: str, part_number: str
) -> list[QuoteRecord]:
    return list(
        db.scalars(
            select(QuoteRecord)
            .where(_customer_matches(QuoteRecord.customer_name, customer_name))
            .where(func.lower(QuoteRecord.part_number) == part_number.lower())
            .order_by(QuoteRecord.quote_date.desc(), QuoteRecord.id.desc())
        )
    )


def _find_replacement_quotes(
    db: Session, customer_name: str, part_number: str
) -> list[QuoteRecord]:
    candidates = db.scalars(
        select(QuoteRecord)
        .where(_customer_matches(QuoteRecord.customer_name, customer_name))
        .where(QuoteRecord.replacement_numbers.is_not(None))
        .order_by(QuoteRecord.quote_date.desc(), QuoteRecord.id.desc())
    )
    part_number_lower = part_number.lower()
    return [
        record
        for record in candidates
        if part_number_lower in _replacement_number_tokens(record.replacement_numbers)
    ]


def _replacement_number_tokens(replacement_numbers: str | None) -> set[str]:
    if not replacement_numbers:
        return set()
    return {
        token.lower()
        for token in REPLACEMENT_NUMBER_SEPARATOR.split(replacement_numbers)
        if token
    }


def _find_contracts(
    db: Session, customer_name: str, part_number: str
) -> list[ContractRecord]:
    return list(
        db.scalars(
            select(ContractRecord)
            .where(_customer_matches(ContractRecord.customer_name, customer_name))
            .where(func.lower(ContractRecord.part_number) == part_number.lower())
            .order_by(ContractRecord.order_date.desc(), ContractRecord.id.desc())
        )
    )


def _customer_matches(column, customer_name: str):
    return func.lower(column).contains(customer_name.lower())


def _serialize_quote(record: QuoteRecord) -> dict[str, object]:
    return {
        "customer_name": record.customer_name,
        "part_number": record.part_number,
        "material_grade": record.material_grade,
        "quantity": record.quantity,
        "unit_price": _serialize_decimal(record.unit_price),
        "currency": record.currency,
        "date": _serialize_date(record.quote_date),
        "source_file": record.source_file,
        "source": "quote",
    }


def _serialize_contract(record: ContractRecord) -> dict[str, object]:
    return {
        "contract_no": record.contract_no,
        "customer_name": record.customer_name,
        "part_number": record.part_number,
        "material_grade": record.material_grade,
        "quantity": record.quantity,
        "unit_price": _serialize_decimal(record.unit_price),
        "currency": record.currency,
        "date": _serialize_date(record.order_date),
        "source_file": record.source_file,
        "source": "contract",
    }


def _serialize_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None
