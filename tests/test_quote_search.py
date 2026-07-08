from datetime import date
from decimal import Decimal

import pytest

from app import database
from app.models import ContractRecord, QuoteRecord
from app.services.quote_search import search_historical_prices


def seed_price_history() -> None:
    with database.SessionLocal() as db:
        db.add_all(
            [
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D1234",
                    replacement_numbers="D-1234-ALT, D9999",
                    material_grade="A+ 半金属",
                    packaging="彩盒",
                    quantity=1000,
                    unit_price=Decimal("2.30"),
                    currency="USD",
                    quote_date=date(2026, 7, 1),
                    source_file="quotes.xlsx",
                ),
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D5678",
                    replacement_numbers="D1234",
                    material_grade="AA",
                    packaging="彩盒",
                    quantity=500,
                    unit_price=Decimal("3.10"),
                    currency="USD",
                    quote_date=date(2026, 7, 2),
                    source_file="quotes.xlsx",
                ),
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D7777",
                    replacement_numbers="ALT-7777",
                    material_grade="NAO",
                    packaging="中性包装",
                    quantity=300,
                    unit_price=Decimal("1.80"),
                    currency="USD",
                    quote_date=date(2026, 7, 3),
                    source_file="quotes-alt.xlsx",
                ),
                QuoteRecord(
                    customer_name="Token Customer",
                    country="UAE",
                    part_number="TK-001",
                    replacement_numbers="KD1, D1234 / OE2",
                    material_grade="Ceramic",
                    packaging="彩盒",
                    quantity=120,
                    unit_price=Decimal("5.10"),
                    currency="USD",
                    quote_date=date(2026, 7, 4),
                    source_file="token-quotes.xlsx",
                ),
                QuoteRecord(
                    customer_name="Token Customer",
                    country="UAE",
                    part_number="TK-002",
                    replacement_numbers="D12345",
                    material_grade="Ceramic",
                    packaging="彩盒",
                    quantity=240,
                    unit_price=Decimal("5.20"),
                    currency="USD",
                    quote_date=date(2026, 7, 5),
                    source_file="substring-quotes.xlsx",
                ),
                ContractRecord(
                    contract_no="HT20260707001",
                    customer_name="Ahmed Trading",
                    country="Libya",
                    order_date=date(2026, 7, 7),
                    part_number="D1234",
                    material_grade="A+ 半金属",
                    packaging="彩盒",
                    quantity=2000,
                    unit_price=Decimal("2.25"),
                    currency="USD",
                    delivery_time="30天",
                    payment_terms="T/T",
                    source_file="contracts.xlsx",
                ),
                ContractRecord(
                    contract_no="HT20260707002",
                    customer_name="Ahmed Trading",
                    country="Libya",
                    order_date=date(2026, 7, 8),
                    part_number="D7777",
                    material_grade="NAO",
                    packaging="中性包装",
                    quantity=800,
                    unit_price=Decimal("1.75"),
                    currency="USD",
                    delivery_time="45天",
                    payment_terms="T/T",
                    source_file="contracts-alt.xlsx",
                ),
            ]
        )
        db.commit()


def test_search_historical_prices_returns_quotes_and_contracts_for_customer_part(
    client,
):
    seed_price_history()

    with database.SessionLocal() as db:
        result = search_historical_prices(db, customer_name="Ahmed", part_number="D1234")

    assert result["found"] is True
    assert result["message"] == "找到历史价格记录"
    assert len(result["quotes"]) == 1
    assert len(result["contracts"]) == 1
    assert result["quotes"][0] == {
        "customer_name": "Ahmed Trading",
        "part_number": "D1234",
        "material_grade": "A+ 半金属",
        "quantity": 1000,
        "unit_price": "2.3000",
        "currency": "USD",
        "date": "2026-07-01",
        "source_file": "quotes.xlsx",
        "source": "quote",
    }
    assert result["contracts"][0]["customer_name"] == "Ahmed Trading"
    assert result["contracts"][0]["contract_no"] == "HT20260707001"
    assert result["contracts"][0]["part_number"] == "D1234"
    assert result["contracts"][0]["unit_price"] == "2.2500"
    assert result["contracts"][0]["date"] == "2026-07-07"
    assert result["contracts"][0]["source"] == "contract"


def test_search_historical_prices_returns_no_records_message(client):
    seed_price_history()

    with database.SessionLocal() as db:
        result = search_historical_prices(db, customer_name="Ahmed", part_number="MISSING")

    assert result == {
        "found": False,
        "message": "未找到历史价格记录",
        "quotes": [],
        "contracts": [],
    }


def test_search_historical_prices_uses_replacement_numbers_only_without_exact_match(
    client,
):
    seed_price_history()

    with database.SessionLocal() as db:
        result = search_historical_prices(
            db, customer_name="Ahmed", part_number="ALT-7777"
        )

    assert result["found"] is True
    assert [record["part_number"] for record in result["quotes"]] == ["D7777"]
    assert result["contracts"] == []


def test_search_historical_prices_matches_replacement_tokens_not_substrings(client):
    seed_price_history()

    with database.SessionLocal() as db:
        result = search_historical_prices(
            db, customer_name="Token", part_number="D1234"
        )

    assert result["found"] is True
    assert [record["part_number"] for record in result["quotes"]] == ["TK-001"]
    assert result["quotes"][0]["customer_name"] == "Token Customer"


@pytest.mark.parametrize(
    "params",
    [
        {"customer": "   ", "part_number": "D1234"},
        {"customer": "Ahmed", "part_number": "   "},
    ],
)
def test_prices_search_endpoint_rejects_blank_values_without_wide_match(
    client, params
):
    seed_price_history()

    response = client.get("/api/search/prices", params=params)

    assert response.status_code == 200
    assert response.json() == {
        "found": False,
        "message": "请输入客户名称和型号",
        "quotes": [],
        "contracts": [],
    }


def test_prices_search_endpoint_returns_history_from_test_database(client):
    seed_price_history()

    response = client.get("/api/search/prices?customer=Ahmed&part_number=D1234")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["quotes"][0]["customer_name"] == "Ahmed Trading"
    assert payload["quotes"][0]["part_number"] == "D1234"
    assert payload["contracts"][0]["contract_no"] == "HT20260707001"
