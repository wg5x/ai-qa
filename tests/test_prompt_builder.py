from datetime import date, datetime, timezone
from decimal import Decimal

from app import database
from app.models import ContractRecord, Material, QuoteRecord, SpeechTemplate
from app.services.ai_provider import (
    FakeAIProvider,
    OpenAICompatibleProvider,
    SalesAnswer,
    generate_sales_answer,
)
from app.services.prompt_builder import build_sales_prompt_context, render_sales_prompt


def seed_prompt_builder_data() -> None:
    with database.SessionLocal() as db:
        db.add_all(
            [
                QuoteRecord(
                    customer_name="Ahmed Trading",
                    country="Libya",
                    part_number="D1234",
                    material_grade="A+ Semi-metallic",
                    packaging="HIQ color box",
                    quantity=1000,
                    unit_price=Decimal("2.30"),
                    currency="USD",
                    quote_date=date(2026, 7, 1),
                    remark="Internal note: supplier cost 1.20, bottom price 2.00.",
                    source_file="ahmed-quotes.xlsx",
                ),
                QuoteRecord(
                    customer_name="Nadia Auto",
                    country="UAE",
                    part_number="B5555",
                    material_grade="Ceramic",
                    packaging="KD neutral box",
                    quantity=5000,
                    unit_price=Decimal("8.80"),
                    currency="USD",
                    quote_date=date(2026, 7, 2),
                    remark="Nadia complete private pricing data.",
                    source_file="nadia-quotes.xlsx",
                ),
                ContractRecord(
                    contract_no="HT-AHMED-001",
                    customer_name="Ahmed Trading",
                    country="Libya",
                    order_date=date(2026, 6, 20),
                    part_number="D1234",
                    material_grade="A+ Semi-metallic",
                    packaging="HIQ color box",
                    quantity=2000,
                    unit_price=Decimal("2.25"),
                    currency="USD",
                    delivery_time="30 days",
                    payment_terms="T/T",
                    source_file="ahmed-contracts.xlsx",
                ),
                ContractRecord(
                    contract_no="HT-NADIA-999",
                    customer_name="Nadia Auto",
                    country="UAE",
                    order_date=date(2026, 6, 21),
                    part_number="B5555",
                    material_grade="Ceramic",
                    packaging="KD neutral box",
                    quantity=9000,
                    unit_price=Decimal("8.10"),
                    currency="USD",
                    delivery_time="45 days",
                    payment_terms="OA",
                    source_file="nadia-contracts.xlsx",
                ),
                Material(
                    name="HIQ Packaging Video",
                    file_path="/materials/hiq-packaging.mp4",
                    material_type="video",
                    product_type="brake_pad",
                    scenario="packaging",
                    brand="HIQ",
                    description="Shows HIQ color box packaging.",
                    recommended_script="You can show the customer the HIQ packaging video.",
                    tags="packaging,HIQ,color box",
                ),
                Material(
                    name="KD Factory Photos",
                    file_path="/materials/kd-factory.jpg",
                    material_type="image",
                    product_type="brake_pad",
                    scenario="factory",
                    brand="KD",
                    description="KD factory private gallery.",
                    recommended_script="Send KD factory photos.",
                    tags="factory,KD",
                ),
                Material(
                    name="Auto Parts Private Packaging",
                    file_path="/materials/auto-parts-private-packaging.pdf",
                    material_type="document",
                    product_type="brake_pad",
                    scenario="packaging",
                    brand="Auto Parts",
                    description="Private packaging guide for Auto Parts brand.",
                    recommended_script="Do not send unless Auto Parts is explicitly requested.",
                    tags="packaging,Auto Parts,private",
                ),
                SpeechTemplate(
                    scenario="price_reply",
                    customer_question="Customer asks for repeat order price.",
                    style_notes="Friendly, concise, confirm history first.",
                    standard_reply="We checked the previous order and can keep the offer stable.",
                    forbidden_words="bottom price, supplier cost",
                    recommended_material_ids="",
                    status="confirmed",
                    confirmed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                ),
                SpeechTemplate(
                    scenario="draft_only",
                    customer_question="Unapproved draft.",
                    style_notes="Do not use.",
                    standard_reply="Draft wording should not appear.",
                    status="draft",
                ),
                SpeechTemplate(
                    scenario="disabled_only",
                    customer_question="Disabled template.",
                    style_notes="Do not use.",
                    standard_reply="Disabled wording should not appear.",
                    status="disabled",
                ),
            ]
        )
        db.commit()


def test_prompt_context_only_includes_records_related_to_customer_and_part(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(
            db, "Ahmed asks whether D1234 can use HIQ color box packaging."
        )

    rendered = render_sales_prompt(context)

    assert context["question"] == "Ahmed asks whether D1234 can use HIQ color box packaging."
    assert "Ahmed Trading" in rendered
    assert "D1234" in rendered
    assert "HT-AHMED-001" in rendered
    assert "HIQ Packaging Video" in rendered
    assert context["speech_templates"] == []
    assert "We checked the previous order" not in rendered
    assert "Nadia Auto" not in rendered
    assert "HT-NADIA-999" not in rendered
    assert "Nadia complete private pricing data" not in rendered
    assert "KD Factory Photos" not in rendered
    assert "Draft wording should not appear" not in rendered
    assert "Disabled wording should not appear" not in rendered


def test_prompt_context_does_not_match_customer_from_common_business_word(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Trading asks whether D1234 is available.")

    rendered = render_sales_prompt(context)

    assert context["extracted_entities"]["customer_name"] is None
    assert context["price_history"]["found"] is False
    assert "Ahmed Trading" not in rendered
    assert "HT-AHMED-001" not in rendered


def test_prompt_context_requires_part_number_token_boundary(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        prefix_context = build_sales_prompt_context(db, "Ahmed asks whether D123 is available.")
        suffix_context = build_sales_prompt_context(db, "Ahmed asks whether XD1234X is available.")

    assert prefix_context["extracted_entities"]["part_number"] is None
    assert suffix_context["extracted_entities"]["part_number"] is None
    assert prefix_context["price_history"]["found"] is False
    assert suffix_context["price_history"]["found"] is False
    assert "Ahmed Trading" not in render_sales_prompt(prefix_context)
    assert "Ahmed Trading" not in render_sales_prompt(suffix_context)


def test_prompt_context_does_not_return_materials_for_generic_words_only(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Please send packaging box video material.")

    rendered = render_sales_prompt(context)

    assert context["materials"] == []
    assert "HIQ Packaging Video" not in rendered
    assert "KD Factory Photos" not in rendered


def test_prompt_context_returns_materials_for_explicit_brand_and_scenario(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        english_context = build_sales_prompt_context(db, "Please send HIQ packaging box video.")
        chinese_context = build_sales_prompt_context(db, "请发送 HIQ 包装素材。")

    assert [material["name"] for material in english_context["materials"]] == [
        "HIQ Packaging Video"
    ]
    assert [material["name"] for material in chinese_context["materials"]] == [
        "HIQ Packaging Video"
    ]


def test_prompt_context_adds_agent_plan_for_material_english_reply(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(
            db, "客户想看 HIQ 包装视频，顺便用英文回复他。"
        )

    agent_plan = context["agent_plan"]
    assert agent_plan["language"] == "en"
    assert agent_plan["intents"] == ["material_recommendation", "customer_reply"]
    assert agent_plan["extracted_entities"]["brand"] == "HIQ"
    assert agent_plan["missing_fields"] == []
    assert agent_plan["tool_usage"]["materials"] == "matched"
    assert "素材库" in agent_plan["required_actions"]
    rendered = render_sales_prompt(context)
    assert "必须直接生成英文客户回复" in rendered
    assert "HIQ Packaging Video" in rendered


def test_prompt_context_marks_quote_question_as_missing_information(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "客户要报价，怎么回复？")

    agent_plan = context["agent_plan"]
    assert agent_plan["intents"] == ["price_lookup", "missing_information", "customer_reply"]
    assert "型号/OE号" in agent_plan["missing_fields"]
    assert "数量" in agent_plan["missing_fields"]
    assert "包装要求" in agent_plan["missing_fields"]
    assert "目的港/国家" in agent_plan["missing_fields"]
    assert "贸易条款" in agent_plan["missing_fields"]
    rendered = render_sales_prompt(context)
    assert "不要生成随机价格" in rendered
    assert "先追问业务员或客户补充信息" in rendered


def test_prompt_context_uses_previous_question_for_translation_follow_up(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(
            db,
            "那英文怎么说？",
            conversation_history=[
                {"role": "user", "content": "客户问刹车片有没有噪音，怎么回复？"},
                {"role": "assistant", "content": "可以说明正常安装后噪音控制稳定。"},
            ],
        )

    agent_plan = context["agent_plan"]
    assert agent_plan["language"] == "en"
    assert agent_plan["is_follow_up"] is True
    assert agent_plan["effective_question"] == "客户问刹车片有没有噪音，怎么回复？ 那英文怎么说？"
    assert "customer_reply" in agent_plan["intents"]
    assert "多轮上下文" in render_sales_prompt(context)


def test_prompt_context_does_not_match_material_from_generic_brand_token(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Please send auto packaging material.")

    rendered = render_sales_prompt(context)

    assert context["materials"] == []
    assert "Auto Parts Private Packaging" not in rendered


def test_prompt_context_only_includes_confirmed_templates_relevant_to_question(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        db.add(
            SpeechTemplate(
                scenario="noise_reply",
                customer_question="客户问刹车片有没有噪音或异响。",
                style_notes="解释磨合期和安装检查，语气专业。",
                standard_reply="我们的刹车片正常安装后噪音控制稳定。",
                status="confirmed",
                confirmed_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            )
        )
        db.commit()
        context = build_sales_prompt_context(db, "客户问刹车片有没有噪音，怎么回复？")

    rendered = render_sales_prompt(context)
    template_replies = [
        template["standard_reply"] for template in context["speech_templates"]
    ]

    assert template_replies == ["我们的刹车片正常安装后噪音控制稳定。"]
    assert "我们的刹车片正常安装后噪音控制稳定。" in rendered
    assert "We checked the previous order" not in rendered
    assert "Draft wording should not appear" not in rendered
    assert "Disabled wording should not appear" not in rendered


def test_prompt_context_omits_confirmed_templates_without_clear_keyword_match(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        db.add(
            SpeechTemplate(
                scenario="generic_reply",
                customer_question="Customer asks a general question.",
                style_notes="Friendly customer reply.",
                standard_reply="Use this customer reply for general conversations.",
                status="confirmed",
                confirmed_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            )
        )
        db.commit()
        context = build_sales_prompt_context(db, "客户需要一段回复话术。")

    rendered = render_sales_prompt(context)

    assert context["speech_templates"] == []
    assert "Use this customer reply for general conversations." not in rendered


def test_generate_sales_answer_filters_sensitive_standard_reply(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Ahmed asks for D1234 best price.")

    rendered = render_sales_prompt(context)
    assert "供应商成本" in rendered
    assert "底价" in rendered
    provider = FakeAIProvider(
        standard_reply="报价公式是供应商成本*1.3，底价2.00，利润空间20%，可报2.30。"
    )

    answer = generate_sales_answer("Ahmed asks for D1234 best price.", context, provider)

    assert "报价公式" not in answer.standard_reply
    assert "供应商成本" not in answer.standard_reply
    assert "底价" not in answer.standard_reply
    assert "利润空间" not in answer.standard_reply
    assert answer.warnings
    assert any("敏感" in warning for warning in answer.warnings)


def test_generate_sales_answer_filters_sensitive_variants(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Ahmed asks for D1234 best price.")

    provider = FakeAIProvider(
        standard_reply=(
            "Our SUPPLIER COSTS, floor-price, and cost   BASIS are internal. "
            "最低价、毛利、利润率都不能发给客户。"
        )
    )

    answer = generate_sales_answer("Ahmed asks for D1234 best price.", context, provider)
    normalized_reply = answer.standard_reply.lower()

    assert "supplier" not in normalized_reply
    assert "floor" not in normalized_reply
    assert "cost" not in normalized_reply
    assert "最低价" not in answer.standard_reply
    assert "毛利" not in answer.standard_reply
    assert "利润率" not in answer.standard_reply
    assert any("移除敏感内容" in warning for warning in answer.warnings)


def test_generate_sales_answer_filters_supplier_possessive_costs(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Ahmed asks for D1234 best price.")

    provider = FakeAIProvider(
        standard_reply="Never share supplier's cost or supplier’s cost with customers."
    )

    answer = generate_sales_answer("Ahmed asks for D1234 best price.", context, provider)
    normalized_reply = answer.standard_reply.lower()

    assert "supplier" not in normalized_reply
    assert "cost" not in normalized_reply
    assert any("移除敏感内容" in warning for warning in answer.warnings)


def test_generate_sales_answer_returns_fixed_structure(client):
    seed_prompt_builder_data()

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "Ahmed asks for D1234 HIQ packaging material.")

    answer = generate_sales_answer(
        "Ahmed asks for D1234 HIQ packaging material.", context, FakeAIProvider()
    )

    assert isinstance(answer, SalesAnswer)
    assert isinstance(answer.reply_thinking, str)
    assert isinstance(answer.standard_reply, str)
    assert isinstance(answer.references, list)
    assert isinstance(answer.recommended_materials, list)
    assert isinstance(answer.warnings, list)
    assert answer.references
    assert answer.recommended_materials


def test_openai_compatible_provider_posts_chat_completion_and_parses_json():
    requests = []

    def fake_transport(url, api_key, payload, timeout):
        requests.append((url, api_key, payload, timeout))
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply_thinking":"reviewed context",'
                            '"standard_reply":"safe customer reply",'
                            '"references":[{"source":"quote"}],'
                            '"recommended_materials":[{"name":"HIQ video"}],'
                            '"warnings":["check price validity"]}'
                        )
                    }
                }
            ]
        }

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://token-gpt.top",
        model="gpt-5.5",
        transport=fake_transport,
    )

    answer = provider.generate(
        "客户问价格怎么回复？",
        {"rendered_prompt": "prompt context"},
    )

    url, api_key, request_payload, timeout = requests[0]
    assert url == "https://token-gpt.top/v1/chat/completions"
    assert api_key == "test-key"
    assert timeout == 60
    assert request_payload["model"] == "gpt-5.5"
    assert "response_format" not in request_payload
    assert "prompt context" in request_payload["messages"][1]["content"]
    assert answer.reply_thinking == "reviewed context"
    assert answer.standard_reply == "safe customer reply"
    assert answer.references == [{"source": "quote"}]
    assert answer.recommended_materials == [{"name": "HIQ video"}]
    assert answer.warnings == ["check price validity"]


def test_openai_compatible_provider_sends_runtime_model_parameters():
    requests = []

    def fake_transport(url, api_key, payload, timeout):
        requests.append(payload)
        return {"choices": [{"message": {"content": '{"standard_reply":"ok"}'}}]}

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://token-gpt.top/v1",
        model="gpt-5.5",
        parameters={"temperature": 0.2, "maxTokens": 2048, "top_p": 0.9},
        transport=fake_transport,
    )

    provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    request_payload = requests[0]
    assert request_payload["temperature"] == 0.2
    assert request_payload["max_tokens"] == 2048
    assert request_payload["top_p"] == 0.9
    assert "maxTokens" not in request_payload


def test_openai_compatible_provider_accepts_v1_base_url():
    requests = []

    def fake_transport(url, api_key, payload, timeout):
        requests.append(url)
        return {"choices": [{"message": {"content": '{"standard_reply":"ok"}'}}]}

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://token-gpt.top/v1",
        model="gpt-5.5",
        transport=fake_transport,
    )

    provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    assert requests == ["https://token-gpt.top/v1/chat/completions"]


def test_openai_compatible_provider_accepts_plain_text_reply():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://token-gpt.top",
        model="gpt-5.5",
        transport=lambda url, api_key, payload, timeout: {
            "choices": [{"message": {"content": "plain customer reply"}}]
        },
    )

    answer = provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    assert answer.reply_thinking == "模型返回了自然语言回复。"
    assert answer.standard_reply == "plain customer reply"
    assert answer.references == []
    assert answer.recommended_materials == []
    assert answer.warnings == []


def test_openai_compatible_provider_retries_transient_transport_errors():
    attempts = []

    def flaky_transport(url, api_key, payload, timeout):
        attempts.append(payload)
        if len(attempts) == 1:
            raise RuntimeError("AI provider request failed: upstream 502")
        return {"choices": [{"message": {"content": '{"standard_reply":"ok"}'}}]}

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://token-gpt.top",
        model="gpt-5.5",
        transport=flaky_transport,
    )

    answer = provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    assert len(attempts) == 2
    assert answer.standard_reply == "ok"
