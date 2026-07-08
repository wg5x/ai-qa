from datetime import date
from decimal import Decimal

from app import database
from app.models import ContractRecord, QuoteRecord
from app.services.order_compare import compare_order_items


def seed_order_history() -> None:
    with database.SessionLocal() as db:
        db.add_all(
            [
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D1234",
                    replacement_numbers="D-1234-ALT",
                    material_grade="A+ Semi-metallic",
                    steel_thickness="5mm",
                    has_shim=True,
                    packaging="Color box",
                    quantity=1000,
                    unit_price=Decimal("2.30"),
                    currency="USD",
                    quote_date=date(2026, 1, 1),
                    source_file="quotes.xlsx",
                )
            ]
        )
        db.commit()


def test_compare_order_items_marks_historical_and_new_parts(client):
    seed_order_history()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Ahmed",
            items=[
                {"part_number": "D1234", "material_grade": "A+ Semi-metallic"},
                {"part_number": "D5678", "material_grade": "Ceramic"},
            ],
            today=date(2026, 3, 1),
        )

    statuses = {item["part_number"]: item["status"] for item in result["items"]}
    assert statuses == {
        "D1234": "historical_part",
        "D5678": "new_part",
    }


def test_compare_order_items_lists_configuration_differences(client):
    seed_order_history()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Ahmed",
            items=[
                {
                    "part_number": "D1234",
                    "replacement_numbers": "D-1234-ALT",
                    "material_grade": "Ceramic",
                    "steel_thickness": "6mm",
                    "has_shim": False,
                    "packaging": "Neutral box",
                    "quantity": 1200,
                    "currency": "EUR",
                    "quote_date": date(2026, 3, 1),
                }
            ],
            today=date(2026, 3, 1),
        )

    item = result["items"][0]
    differences = {difference["field"]: difference for difference in item["differences"]}
    assert differences["material_grade"] == {
        "field": "material_grade",
        "old_value": "A+ Semi-metallic",
        "new_value": "Ceramic",
    }
    assert differences["steel_thickness"]["old_value"] == "5mm"
    assert differences["steel_thickness"]["new_value"] == "6mm"
    assert differences["has_shim"]["old_value"] is True
    assert differences["has_shim"]["new_value"] is False
    assert differences["packaging"]["old_value"] == "Color box"
    assert differences["packaging"]["new_value"] == "Neutral box"
    assert differences["quantity"]["old_value"] == 1000
    assert differences["quantity"]["new_value"] == 1200
    assert differences["currency"]["old_value"] == "USD"
    assert differences["currency"]["new_value"] == "EUR"
    assert item["needs_requote"] is True


def test_compare_order_items_flags_stale_quote_date_for_requote(client):
    seed_order_history()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Ahmed",
            items=[{"part_number": "D1234"}],
            today=date(2026, 8, 1),
        )

    item = result["items"][0]
    assert item["status"] == "historical_part"
    assert item["needs_requote"] is True
    assert {
        "field": "quote_date",
        "old_value": "2026-01-01",
        "new_value": None,
    } in item["differences"]


def test_compare_order_items_uses_quote_date_not_contract_order_date_for_requote(
    client,
):
    with database.SessionLocal() as db:
        db.add_all(
            [
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    part_number="D2468",
                    material_grade="Ceramic",
                    packaging="Color box",
                    quantity=1000,
                    currency="USD",
                    quote_date=date(2026, 1, 1),
                    source_file="old-quote.xlsx",
                ),
                ContractRecord(
                    contract_no="HT20260730001",
                    customer_name="Ahmed Trading",
                    order_date=date(2026, 7, 30),
                    part_number="D2468",
                    material_grade="Ceramic",
                    packaging="Color box",
                    quantity=1000,
                    currency="USD",
                    source_file="recent-contract.xlsx",
                ),
            ]
        )
        db.commit()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Ahmed",
            items=[
                {
                    "part_number": "D2468",
                    "material_grade": "Ceramic",
                    "packaging": "Color box",
                    "quantity": 1000,
                    "currency": "USD",
                }
            ],
            today=date(2026, 8, 1),
        )

    item = result["items"][0]
    assert item["status"] == "historical_part"
    assert item["quote_history"]["date"] == "2026-01-01"
    assert item["contract_history"]["date"] == "2026-07-30"
    assert item["needs_requote"] is True
    assert {
        "field": "quote_date",
        "old_value": "2026-01-01",
        "new_value": None,
    } in item["differences"]


def test_compare_order_items_flags_missing_required_fields_for_manual_review(client):
    seed_order_history()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Ahmed",
            items=[{"part_number": "D1234"}],
            today=date(2026, 3, 1),
        )

    item = result["items"][0]
    assert item["status"] == "historical_part"
    assert item["missing_fields"] == [
        "material_grade",
        "packaging",
        "quantity",
        "currency",
    ]
    assert item["requires_manual_review"] is True
    assert item["needs_requote"] is True


def test_compare_order_items_matches_replacement_tokens_with_task5_separators(client):
    with database.SessionLocal() as db:
        db.add(
            QuoteRecord(
                customer_name="Token Customer",
                part_number="TK-001",
                replacement_numbers="KD1, D1234 / OE2\nALT；ZZ、QQ D8888",
                material_grade="Ceramic",
                packaging="Color box",
                quantity=1000,
                currency="USD",
                quote_date=date(2026, 7, 1),
                source_file="token-quote.xlsx",
            )
        )
        db.commit()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Token",
            items=[
                {
                    "part_number": "D1234",
                    "material_grade": "Ceramic",
                    "packaging": "Color box",
                    "quantity": 1000,
                    "currency": "USD",
                }
            ],
            today=date(2026, 7, 2),
        )

    item = result["items"][0]
    assert item["status"] == "historical_part"
    assert item["quote_history"]["part_number"] == "TK-001"


def test_compare_order_items_does_not_match_replacement_substrings(client):
    with database.SessionLocal() as db:
        db.add(
            QuoteRecord(
                customer_name="Substring Customer",
                part_number="TK-002",
                replacement_numbers="D12345",
                material_grade="Ceramic",
                packaging="Color box",
                quantity=1000,
                currency="USD",
                quote_date=date(2026, 7, 1),
                source_file="substring-quote.xlsx",
            )
        )
        db.commit()

    with database.SessionLocal() as db:
        result = compare_order_items(
            db,
            customer_name="Substring",
            items=[
                {
                    "part_number": "D1234",
                    "material_grade": "Ceramic",
                    "packaging": "Color box",
                    "quantity": 1000,
                    "currency": "USD",
                }
            ],
            today=date(2026, 7, 2),
        )

    item = result["items"][0]
    assert item["status"] == "new_part"
    assert item["quote_history"] is None


def test_orders_compare_endpoint_returns_comparison(client):
    seed_order_history()

    response = client.post(
        "/api/orders/compare",
        json={
            "customer_name": "Ahmed",
            "items": [
                {"part_number": "D1234", "material_grade": "A+ Semi-metallic"},
                {"part_number": "D5678", "material_grade": "Ceramic"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["customer_name"] == "Ahmed"
    statuses = {item["part_number"]: item["status"] for item in payload["items"]}
    assert statuses == {
        "D1234": "historical_part",
        "D5678": "new_part",
    }
