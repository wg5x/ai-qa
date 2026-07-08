from datetime import date
from decimal import Decimal

from app import database
from app.models import ContractRecord, QuoteRecord
from app.services.ai_provider import SENSITIVE_TERMS
import app.routers.qa as qa_router
from app.services.material_search import create_material
from app.services.prompt_builder import build_sales_prompt_context


def seed_acceptance_price_history() -> None:
    with database.SessionLocal() as db:
        db.add_all(
            [
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D1234",
                    material_grade="A+ 半金属",
                    packaging="彩盒",
                    quantity=1000,
                    unit_price=Decimal("2.30"),
                    currency="USD",
                    quote_date=date(2026, 7, 1),
                    source_file="quotes.xlsx",
                ),
                ContractRecord(
                    contract_no="HT20260707001",
                    customer_name="Ahmed Trading",
                    country="Libya",
                    order_date=date(2026, 6, 15),
                    part_number="D1234",
                    material_grade="A+ 半金属",
                    packaging="彩盒",
                    quantity=2000,
                    unit_price=Decimal("2.25"),
                    currency="USD",
                    source_file="contracts.xlsx",
                ),
            ]
        )
        db.commit()


def test_health_returns_ok_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_page_routes_return_html(client):
    pages = [
        ("/", "AI 问答"),
        ("/knowledge", "知识库管理"),
        ("/materials", "素材管理"),
        ("/speech-templates", "话术模板"),
    ]

    for path, title in pages:
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert title in response.text
        assert "/static/app.css" in response.text
        assert "/static/app.js" in response.text


def test_qa_ask_returns_structured_chinese_answer_without_sensitive_terms(client):
    response = client.post(
        "/api/qa/ask",
        json={"question": "客户问刹车片有没有噪音，怎么回复？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "reply_thinking",
        "standard_reply",
        "references",
        "recommended_materials",
        "warnings",
    }
    assert isinstance(payload["reply_thinking"], str)
    assert isinstance(payload["standard_reply"], str)
    assert isinstance(payload["references"], list)
    assert isinstance(payload["recommended_materials"], list)
    assert isinstance(payload["warnings"], list)
    assert "刹车片" in payload["standard_reply"] or "客户" in payload["standard_reply"]
    assert not any(term in payload["standard_reply"] for term in SENSITIVE_TERMS)


def test_qa_ask_rejects_blank_question(client):
    response = client.post("/api/qa/ask", json={"question": "   "})

    assert response.status_code == 400


def test_qa_ask_returns_502_when_ai_provider_fails(client, monkeypatch):
    def fail_provider(question, context):
        raise RuntimeError("AI provider request failed: upstream 502")

    monkeypatch.setattr(qa_router, "generate_sales_answer", fail_provider)

    response = client.post(
        "/api/qa/ask",
        json={"question": "客户问刹车片有没有噪音，怎么回复？"},
    )

    assert response.status_code == 502
    assert "AI provider request failed" in response.json()["detail"]


def test_acceptance_case_1_common_noise_question_reply(client):
    response = client.post(
        "/api/qa/ask",
        json={"question": "客户问刹车片有没有噪音，怎么回复？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply_thinking"]
    assert payload["standard_reply"]
    assert isinstance(payload["recommended_materials"], list)
    assert not any(term in payload["standard_reply"] for term in SENSITIVE_TERMS)


def test_acceptance_case_2_historical_price_lookup(client):
    seed_acceptance_price_history()

    response = client.get("/api/search/prices?customer=Ahmed&part_number=D1234")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["quotes"][0]["part_number"] == "D1234"
    assert payload["quotes"][0]["material_grade"] == "A+ 半金属"
    assert payload["quotes"][0]["unit_price"] == "2.3000"
    assert payload["quotes"][0]["currency"] == "USD"
    assert payload["contracts"][0]["contract_no"] == "HT20260707001"

    missing = client.get("/api/search/prices?customer=Ahmed&part_number=MISSING")
    assert missing.json()["found"] is False


def test_acceptance_case_3_order_compare(client):
    seed_acceptance_price_history()

    response = client.post(
        "/api/orders/compare",
        json={
            "customer_name": "Ahmed",
            "part_numbers": ["D1234", "D5678"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    statuses = {item["part_number"]: item["status"] for item in payload["items"]}
    assert statuses["D1234"] == "historical_part"
    assert statuses["D5678"] == "new_part"
    item_flags = {item["part_number"]: item["needs_requote"] for item in payload["items"]}
    assert item_flags["D5678"] is True


def test_acceptance_case_4_hiq_packaging_material_recommendation(client):
    with database.SessionLocal() as db:
        create_material(
            db,
            {
                "name": "HIQ 包装视频",
                "file_path": "/Users/sales/materials/hiq-packaging.mp4",
                "material_type": "video",
                "product_type": "brake_pad",
                "scenario": "包装效果",
                "brand": "HIQ",
                "description": "HIQ 包装实拍，可用于展示彩盒效果。",
                "recommended_script": "这是我们 HIQ 包装的实拍效果，颜色和图案都比较清晰。",
                "tags": "包装,HIQ,视频",
            },
        )

    qa_response = client.post(
        "/api/qa/ask",
        json={"question": "客户想看 HIQ 包装效果。"},
    )
    assert qa_response.status_code == 200
    qa_payload = qa_response.json()
    assert qa_payload["standard_reply"]

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "客户想看 HIQ 包装效果。")

    assert context["materials"]
    assert context["materials"][0]["brand"] == "HIQ"


def test_acceptance_case_5_speech_template_confirm_flow(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()
    assert draft["status"] == "draft"

    with database.SessionLocal() as db:
        before_confirm = build_sales_prompt_context(db, "客户问刹车片有没有噪音，怎么回复？")
    assert before_confirm["speech_templates"] == []

    confirmed = client.post(f"/api/templates/{draft['id']}/confirm").json()
    assert confirmed["status"] == "confirmed"

    with database.SessionLocal() as db:
        after_confirm = build_sales_prompt_context(db, "客户问刹车片有没有噪音，怎么回复？")
    assert after_confirm["speech_templates"]
    assert after_confirm["speech_templates"][0]["id"] == confirmed["id"]
