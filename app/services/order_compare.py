from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ContractRecord, QuoteRecord
from app.services.quote_search import REPLACEMENT_NUMBER_SEPARATOR


COMPARE_FIELDS = (
    "part_number",
    "replacement_numbers",
    "material_grade",
    "steel_thickness",
    "has_shim",
    "packaging",
    "quantity",
    "currency",
    "quote_date",
)
REQUOTE_FIELDS = {
    "material_grade",
    "steel_thickness",
    "packaging",
    "quantity",
    "currency",
    "quote_date",
}
REQUIRED_ORDER_FIELDS = ("material_grade", "packaging", "quantity", "currency")
STALE_QUOTE_DAYS = 180


def compare_order_items(
    db: Session,
    customer_name: str,
    items: list[dict[str, Any]],
    today: date | None = None,
) -> dict[str, object]:
    comparison_date = today or date.today()
    compared_items = [
        _compare_item(db, customer_name, item, comparison_date) for item in items
    ]
    return {"customer_name": customer_name, "items": compared_items}


def _compare_item(
    db: Session,
    customer_name: str,
    item: dict[str, Any],
    today: date,
) -> dict[str, object]:
    part_number = _clean_text(item.get("part_number"))
    quote_history = _find_latest_quote(db, customer_name, part_number)
    contract_history = _find_latest_contract(db, customer_name, part_number)
    missing_fields = _missing_required_fields(item)
    requires_manual_review = bool(missing_fields)
    if quote_history is None and contract_history is None:
        return {
            "part_number": part_number,
            "status": "new_part",
            "matched_history": None,
            "quote_history": None,
            "contract_history": None,
            "differences": [],
            "missing_fields": missing_fields,
            "requires_manual_review": requires_manual_review,
            "needs_requote": True,
        }

    comparison_history = quote_history or contract_history
    historical_values = _history_values(comparison_history)
    differences = _differences(historical_values, item)
    stale_quote = (
        _is_stale_quote(quote_history.quote_date, today)
        if quote_history is not None
        else False
    )
    if stale_quote and "quote_date" not in {diff["field"] for diff in differences}:
        differences.append(
            {
                "field": "quote_date",
                "old_value": _serialize_value(quote_history.quote_date),
                "new_value": _serialize_value(item.get("quote_date")),
            }
        )

    needs_requote = (
        requires_manual_review
        or stale_quote
        or quote_history is None
        or any(diff["field"] in REQUOTE_FIELDS for diff in differences)
    )
    matched_history = quote_history or contract_history
    return {
        "part_number": part_number,
        "status": "historical_part",
        "matched_history": _serialize_history(matched_history),
        "quote_history": _serialize_history(quote_history) if quote_history else None,
        "contract_history": _serialize_history(contract_history)
        if contract_history
        else None,
        "differences": differences,
        "missing_fields": missing_fields,
        "requires_manual_review": requires_manual_review,
        "needs_requote": needs_requote,
    }


def _missing_required_fields(item: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_ORDER_FIELDS if _is_missing(item.get(field))]


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _find_latest_quote(
    db: Session, customer_name: str, part_number: str | None
) -> QuoteRecord | None:
    if not customer_name.strip() or not part_number:
        return None

    exact_quotes = list(
        db.scalars(
            select(QuoteRecord)
            .where(_customer_matches(QuoteRecord.customer_name, customer_name))
            .where(func.lower(QuoteRecord.part_number) == part_number.lower())
            .order_by(QuoteRecord.quote_date.desc(), QuoteRecord.id.desc())
        )
    )
    candidates = exact_quotes or _find_replacement_quotes(db, customer_name, part_number)
    return max(candidates, key=_quote_sort_key, default=None)


def _find_latest_contract(
    db: Session, customer_name: str, part_number: str | None
) -> ContractRecord | None:
    if not customer_name.strip() or not part_number:
        return None

    return db.scalars(
        select(ContractRecord)
        .where(_customer_matches(ContractRecord.customer_name, customer_name))
        .where(func.lower(ContractRecord.part_number) == part_number.lower())
        .order_by(ContractRecord.order_date.desc(), ContractRecord.id.desc())
    ).first()


def _quote_sort_key(record: QuoteRecord) -> tuple[date, int]:
    return (record.quote_date or date.min, record.id)


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
        if part_number_lower in _replacement_tokens(record.replacement_numbers)
    ]


def _customer_matches(column, customer_name: str):
    return func.lower(column).contains(customer_name.lower())


def _replacement_tokens(replacement_numbers: str | None) -> set[str]:
    if not replacement_numbers:
        return set()
    return {
        token.strip().lower()
        for token in REPLACEMENT_NUMBER_SEPARATOR.split(replacement_numbers)
        if token.strip()
    }


def _history_values(record: QuoteRecord | ContractRecord) -> dict[str, Any]:
    values = {
        "part_number": record.part_number,
        "material_grade": record.material_grade,
        "packaging": record.packaging,
        "quantity": record.quantity,
        "currency": record.currency,
    }
    if isinstance(record, QuoteRecord):
        values.update(
            {
                "replacement_numbers": record.replacement_numbers,
                "steel_thickness": record.steel_thickness,
                "has_shim": record.has_shim,
                "quote_date": record.quote_date,
            }
        )
    return values


def _differences(
    historical_values: dict[str, Any], item: dict[str, Any]
) -> list[dict[str, object]]:
    differences = []
    for field in COMPARE_FIELDS:
        if field not in item:
            continue
        if field not in historical_values:
            continue
        old_value = historical_values.get(field)
        new_value = item.get(field)
        if _serialize_value(old_value) != _serialize_value(new_value):
            differences.append(
                {
                    "field": field,
                    "old_value": _serialize_value(old_value),
                    "new_value": _serialize_value(new_value),
                }
            )
    return differences


def _is_stale_quote(value: Any, today: date) -> bool:
    quote_date = _parse_date(value)
    return quote_date is not None and (today - quote_date).days > STALE_QUOTE_DAYS


def _serialize_history(record: QuoteRecord | ContractRecord) -> dict[str, object]:
    values = _history_values(record)
    history_date = (
        record.quote_date if isinstance(record, QuoteRecord) else record.order_date
    )
    return {
        "source": "quote" if isinstance(record, QuoteRecord) else "contract",
        "part_number": values["part_number"],
        "date": _serialize_value(history_date),
        "source_file": record.source_file,
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _serialize_value(value: Any) -> object:
    if isinstance(value, date):
        return value.isoformat()
    return value
