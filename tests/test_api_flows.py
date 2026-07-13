from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from openpyxl import Workbook

from app import database
from app.models import ContractRecord, Material, QuoteRecord
from app.services.ai_provider import SENSITIVE_TERMS, SalesAnswer
import app.routers.qa as qa_router
from app.services.material_search import create_material
from app.services.prompt_builder import build_sales_prompt_context


def _quote_workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "客户名称",
        "国家/地区",
        "型号",
        "材质等级",
        "包装方式",
        "数量",
        "单价",
        "币种",
        "报价日期",
    ])
    sheet.append(["Ahmed", "Libya", "D1234", "A+ 半金属", "彩盒", 1000, 2.3, "USD", date(2026, 7, 1)])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _contract_workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "合同编号",
        "客户名称",
        "国家/地区",
        "下单日期",
        "型号",
        "材质等级",
        "包装方式",
        "数量",
        "单价",
        "币种",
    ])
    sheet.append(["HT20260709001", "Ahmed", "Libya", date(2026, 7, 9), "D1234", "A+ 半金属", "彩盒", 1000, 2.3, "USD"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
        + "</w:body></w:document>"
    )
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return stream.getvalue()


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


def test_favicon_request_does_not_log_404(client):
    response = client.get("/favicon.ico")
    head_response = client.head("/favicon.ico")

    assert response.status_code == 204
    assert head_response.status_code == 204


def test_page_routes_return_html(client):
    pages = [
        ("/", "AI 问答"),
        ("/knowledge", "知识库管理"),
        ("/materials", "素材库"),
        ("/speech-templates", "话术库"),
    ]

    for path, title in pages:
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert title in response.text
        assert "/static/app.css" in response.text
        assert "/static/app.js?v=" in response.text


def test_page_shell_uses_left_sidebar_navigation(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'class="app-shell"' in response.text
    assert 'class="sidebar-nav"' in response.text
    assert ">知识库<" in response.text
    assert ">素材库<" in response.text
    assert ">话术库<" in response.text
    assert 'class="page-content"' in response.text
    assert 'class="main-nav"' not in response.text


def test_materials_page_uses_list_with_create_modal(client):
    response = client.get("/materials")

    assert response.status_code == 200
    assert "素材库" in response.text
    assert 'id="import-raw-materials"' not in response.text
    assert "导入素材库" not in response.text
    assert 'id="material-search-form"' not in response.text
    assert 'id="material-refresh"' not in response.text
    assert "搜索名称、品牌、型号、标签或描述" not in response.text
    assert 'id="open-material-modal"' in response.text
    assert 'id="import-manual-knowledge"' not in response.text
    assert 'id="material-modal"' in response.text
    assert 'class="modal hidden"' in response.text
    assert 'class="file-picker"' in response.text
    assert 'id="material-file-path"' in response.text
    assert 'id="material-file-upload"' in response.text
    assert 'accept="image/*,video/*"' in response.text
    assert '.pdf' not in response.text
    assert 'id="material-auto-tag"' in response.text
    assert response.text.count('name="file_path"') == 1
    assert 'id="material-review-scan-form"' not in response.text
    assert 'id="material-review-list"' not in response.text
    assert 'id="material-list"' in response.text
    assert 'id="material-form"' in response.text
    assert 'id="material-id"' in response.text


def test_knowledge_page_has_manual_import_action(client):
    response = client.get("/knowledge")

    assert response.status_code == 200
    assert 'id="open-knowledge-modal"' in response.text
    assert 'id="knowledge-modal"' in response.text
    assert 'id="knowledge-import-form"' in response.text
    assert 'id="knowledge-file-upload"' in response.text
    assert 'id="create-knowledge-data"' in response.text
    assert 'id="knowledge-list"' in response.text
    assert 'id="knowledge-pagination"' in response.text
    assert 'id="knowledge-edit-modal"' in response.text
    assert 'id="knowledge-edit-form"' in response.text
    assert 'id="quote-import-form"' not in response.text
    assert 'id="contract-import-form"' not in response.text
    assert 'id="import-manual-knowledge"' not in response.text
    assert "新增知识" in response.text
    assert "知识类型" not in response.text
    assert "后台解析后自动生成知识库记录" in response.text
    assert "导入默认报价单、合同和谈单手册" not in response.text
    assert "导入知识库" not in response.text
    assert "创建知识库" not in response.text
    assert "知识库列表" in response.text


def test_knowledge_frontend_imports_manual(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    knowledge_script = response.text.split("function initKnowledgePage()", 1)[1].split(
        "function materialCard", 1
    )[0]
    materials_script = response.text.split("function initMaterialsPage()", 1)[1].split(
        "function statusLabel", 1
    )[0]
    assert 'document.getElementById("open-knowledge-modal")' in knowledge_script
    assert 'document.getElementById("create-knowledge-data")' in knowledge_script
    assert "/api/imports/knowledge" in knowledge_script
    assert "/api/imports/knowledge/items" in knowledge_script
    assert "/api/imports/knowledge/upload" in knowledge_script
    assert "/api/imports/knowledge/${item.source_type}/${knowledgeId}" in knowledge_script
    assert "edit-knowledge" in knowledge_script
    assert "loadKnowledgeItems" in knowledge_script
    assert 'document.getElementById("open-knowledge-modal")' not in materials_script


def test_knowledge_frontend_renders_edit_action_for_every_item_type(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    knowledge_script = response.text.split("function initKnowledgePage()", 1)[1].split(
        "function materialCard", 1
    )[0]
    assert 'class="btn ghost edit-knowledge"' in knowledge_script
    assert 'item.source_type === "manual"' not in knowledge_script
    assert "/api/imports/knowledge/${item.source_type}/${knowledgeId}" in knowledge_script


def test_speech_templates_page_is_named_speech_library(client):
    response = client.get("/speech-templates")

    assert response.status_code == 200
    assert "话术库" in response.text
    assert "导入对话文本" in response.text
    assert "人工确认后进入可用话术库" in response.text
    assert "话术库列表" in response.text
    assert 'id="open-speech-import-modal"' in response.text
    assert 'id="speech-import-modal"' in response.text
    assert 'id="chat-summarize-form"' in response.text
    assert 'id="template-editor"' in response.text
    assert 'class="modal hidden"' in response.text
    assert "话术模板" not in response.text


def test_speech_templates_frontend_uses_modal_flow(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    speech_script = response.text.split("function initSpeechTemplatesPage()", 1)[1]
    assert 'document.getElementById("open-speech-import-modal")' in speech_script
    assert 'document.getElementById("speech-import-modal")' in speech_script
    assert 'document.getElementById("template-editor")?.classList.remove("hidden")' in response.text
    assert "closeSpeechImportModal" in speech_script
    assert "closeTemplateEditor" in speech_script


def test_materials_frontend_auto_tags_after_file_upload(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    materials_script = response.text.split("function initMaterialsPage()", 1)[1].split(
        "function statusLabel", 1
    )[0]
    assert 'document.getElementById("import-raw-materials")' not in materials_script
    assert 'document.getElementById("material-search-form")' not in materials_script
    assert 'document.getElementById("material-refresh")' not in materials_script
    assert "/api/imports/materials" not in materials_script
    assert "async function autoTagCurrentMaterial" in response.text
    assert 'fileUpload?.addEventListener("change", async' in response.text
    assert "await autoTagCurrentMaterial()" in response.text
    assert "/api/materials/upload" in response.text
    assert "/api/material-reviews/analyze" in response.text
    assert "distribution_id: currentDistributionId" in response.text


def test_import_manual_endpoint_imports_default_manual_once(client):
    first_response = client.post("/api/imports/manual")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["paragraphs_found"] > 0
    assert first_payload["created"] > 0
    assert first_payload["created"] + first_payload["skipped"] == first_payload["paragraphs_found"]
    assert first_payload["source_file"].endswith("raw/260706业务员谈单手册_v4.0.docx")

    second_response = client.post("/api/imports/manual")

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["paragraphs_found"] == first_payload["paragraphs_found"]
    assert second_payload["created"] == 0
    assert second_payload["skipped"] == first_payload["paragraphs_found"]


def test_manual_fragments_endpoint_lists_imported_knowledge(client):
    import_response = client.post("/api/imports/manual")
    assert import_response.status_code == 200

    list_response = client.get(
        "/api/imports/manual/fragments",
        params={"page": 1, "page_size": 5},
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == import_response.json()["created"]
    assert payload["page"] == 1
    assert payload["page_size"] == 5
    assert len(payload["items"]) == 5
    assert payload["items"][0]["material_type"] == "knowledge"
    assert payload["items"][0]["scenario"] == "谈单知识"


def test_knowledge_items_include_existing_manual_fragments(client):
    import_response = client.post("/api/imports/manual")
    assert import_response.status_code == 200

    list_response = client.get(
        "/api/imports/knowledge/items",
        params={"page": 1, "page_size": 100},
    )

    assert list_response.status_code == 200
    manual_items = [
        item for item in list_response.json()["items"] if item["source_type"] == "manual"
    ]
    assert manual_items
    assert "260706业务员谈单手册_v4.0.docx" in manual_items[0]["source_file"]
    assert "tags" in manual_items[0]


def test_update_knowledge_endpoint_updates_quote_card_without_structured_fields(client):
    import_response = client.post("/api/imports/knowledge")
    assert import_response.status_code == 200
    quote_item = [
        item
        for item in client.get(
            "/api/imports/knowledge/items",
            params={"page": 1, "page_size": 100},
        ).json()["items"]
        if item["source_type"] == "quote"
    ][0]

    response = client.patch(
        f"/api/imports/knowledge/quote/{quote_item['raw_id']}",
        json={
            "title": "编辑后的报价知识",
            "description": "编辑后的报价说明，方便知识库检索。",
            "tags": "报价,重点客户",
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "编辑后的报价知识"

    updated = [
        item
        for item in client.get(
            "/api/imports/knowledge/items",
            params={"page": 1, "page_size": 100},
        ).json()["items"]
        if item["source_type"] == "quote" and item["raw_id"] == quote_item["raw_id"]
    ][0]
    assert updated["title"] == "编辑后的报价知识"
    assert updated["description"] == "编辑后的报价说明，方便知识库检索。"
    assert updated["tags"] == "报价,重点客户"

    with database.SessionLocal() as db:
        record = db.get(QuoteRecord, quote_item["raw_id"])
        assert record.customer_name == "Ahmed"
        assert record.part_number == "D1234"


def test_update_knowledge_endpoint_updates_contract_card(client):
    import_response = client.post("/api/imports/knowledge")
    assert import_response.status_code == 200
    contract_item = [
        item
        for item in client.get(
            "/api/imports/knowledge/items",
            params={"page": 1, "page_size": 100},
        ).json()["items"]
        if item["source_type"] == "contract"
    ][0]

    response = client.patch(
        f"/api/imports/knowledge/contract/{contract_item['raw_id']}",
        json={
            "title": "编辑后的合同知识",
            "description": "编辑后的合同说明。",
            "tags": "合同,交付",
        },
    )

    assert response.status_code == 200
    updated = [
        item
        for item in client.get(
            "/api/imports/knowledge/items",
            params={"page": 1, "page_size": 100},
        ).json()["items"]
        if item["source_type"] == "contract" and item["raw_id"] == contract_item["raw_id"]
    ][0]
    assert updated["title"] == "编辑后的合同知识"
    assert updated["description"] == "编辑后的合同说明。"
    assert updated["tags"] == "合同,交付"


def test_update_knowledge_endpoint_updates_manual_text_fragment(client):
    import_response = client.post("/api/imports/manual")
    assert import_response.status_code == 200
    manual_id = [
        item
        for item in client.get(
            "/api/imports/knowledge/items",
            params={"page": 1, "page_size": 100},
        ).json()["items"]
        if item["source_type"] == "manual"
    ][0]["raw_id"]

    response = client.patch(
        f"/api/imports/knowledge/manual/{manual_id}",
        json={
            "title": "更新后的谈单标题",
            "description": "更新后的谈单内容，方便业务员检索和引用。",
            "tags": "谈单,客户异议",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_id"] == manual_id
    assert payload["title"] == "更新后的谈单标题"
    assert payload["description"] == "更新后的谈单内容，方便业务员检索和引用。"
    assert payload["tags"] == "谈单,客户异议"

    list_response = client.get(
        "/api/imports/knowledge/items",
        params={"page": 1, "page_size": 100},
    )
    updated = [
        item
        for item in list_response.json()["items"]
        if item["source_type"] == "manual" and item["raw_id"] == manual_id
    ][0]
    assert updated["title"] == "更新后的谈单标题"
    assert updated["description"] == "更新后的谈单内容，方便业务员检索和引用。"
    assert updated["tags"] == "谈单,客户异议"


def test_update_manual_knowledge_endpoint_rejects_non_knowledge_material(client):
    with database.SessionLocal() as db:
        material = Material(
            name="产品素材",
            file_path="/tmp/product.png",
            material_type="image",
            description="这不是文本知识片段",
        )
        db.add(material)
        db.commit()
        material_id = material.id

    response = client.patch(
        f"/api/imports/knowledge/manual/{material_id}",
        json={"title": "不应该更新", "description": "不应该更新"},
    )

    assert response.status_code == 404


def test_import_knowledge_endpoint_imports_quotes_contracts_and_manual(client):
    first_response = client.post("/api/imports/knowledge")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["quotes"]["imported_count"] > 0
    assert first_payload["contracts"]["imported_count"] > 0
    assert first_payload["manual"]["created"] > 0

    list_response = client.get(
        "/api/imports/knowledge/items",
        params={"page": 1, "page_size": 100},
    )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    item_types = {item["source_type"] for item in list_payload["items"]}
    assert {"quote", "contract", "manual"}.issubset(item_types)

    second_response = client.post("/api/imports/knowledge")

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["quotes"]["imported_count"] == 0
    assert second_payload["contracts"]["imported_count"] == 0
    assert second_payload["manual"]["created"] == 0


def test_upload_knowledge_endpoint_imports_quote_excel(client):
    response = client.post(
        "/api/imports/knowledge/upload",
        files={
            "file": (
                "uploaded-quotes.xlsx",
                _quote_workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "quote"
    assert payload["result"]["imported_count"] == 1

    list_response = client.get(
        "/api/imports/knowledge/items",
        params={"page": 1, "page_size": 20},
    )
    quote_items = [item for item in list_response.json()["items"] if item["source_type"] == "quote"]
    assert quote_items
    assert "uploaded-quotes" in quote_items[0]["source_file"]
    assert quote_items[0]["source_file"].endswith(".xlsx")


def test_upload_knowledge_endpoint_imports_contract_excel(client):
    response = client.post(
        "/api/imports/knowledge/upload",
        files={
            "file": (
                "uploaded-contracts.xlsx",
                _contract_workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "contract"
    assert payload["result"]["imported_count"] == 1


def test_upload_knowledge_endpoint_imports_manual_docx(client):
    response = client.post(
        "/api/imports/knowledge/upload",
        files={
            "file": (
                "uploaded-manual.docx",
                _docx_bytes(["客户关心噪音时，先说明产品经过装车测试，再解释材料配方。"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "manual"
    assert payload["result"]["created"] == 1


def test_upload_knowledge_endpoint_rejects_unsupported_file_type(client):
    response = client.post(
        "/api/imports/knowledge/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400


def test_import_materials_endpoint_imports_default_media_once(client):
    first_response = client.post("/api/imports/materials")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["created"] > 0
    assert first_payload["skipped"] == 0
    assert first_payload["media_dir"].endswith("raw/2026.7.7刹车片/小片")

    list_response = client.get("/api/materials", params={"page": 1, "page_size": 5})
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == first_payload["created"]
    assert len(list_payload["items"]) == 5
    assert all(item["material_type"] != "knowledge" for item in list_payload["items"])

    second_response = client.post("/api/imports/materials")

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["created"] == 0
    assert second_payload["skipped"] == first_payload["created"]


def test_material_upload_rejects_pdf_as_non_material(client):
    response = client.post(
        "/api/materials/upload",
        files={"file": ("catalog.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400


def test_qa_page_uses_chat_workspace(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'class="qa-workspace"' in response.text
    assert 'id="chat-thread"' in response.text
    assert 'id="latest-question"' in response.text
    assert 'class="chat-composer"' in response.text
    assert 'id="qa-result"' in response.text


def test_static_styles_size_sidebar_and_content_for_desktop(client):
    response = client.get("/static/app.css")

    assert response.status_code == 200
    assert "--sidebar-width: 260px;" in response.text
    assert "max-width: 1440px;" in response.text


def test_qa_frontend_sends_conversation_history(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "qaConversationHistory" in response.text
    assert "conversation_history" in response.text
    assert "currentDistributionId" in response.text
    assert "distribution_id" in response.text
    assert "loadDistributionRuntimeConfig" in response.text
    assert "applyDistributionRuntimeConfig" in response.text
    assert "/dist/api/runtime/distributions" in response.text
    assert 'path.startsWith("/dist/")' in response.text


def test_qa_frontend_persists_distribution_id_across_pages(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "DISTRIBUTION_ID_STORAGE_KEY" in response.text
    assert "sessionStorage.setItem" in response.text
    assert "sessionStorage.getItem" in response.text
    assert "syncDistributionNavigationLinks" in response.text
    assert 'url.searchParams.set("id", currentDistributionId)' in response.text


def test_qa_frontend_renders_recommended_image_and_video_cards(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "renderMaterialPreview" in response.text
    assert "<img" in response.text
    assert "<video" in response.text
    assert "material.file_url" in response.text


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
    def fail_provider(question, context, provider=None):
        raise RuntimeError("AI provider request failed: upstream 502")

    monkeypatch.setattr(qa_router, "generate_sales_answer", fail_provider)

    response = client.post(
        "/api/qa/ask",
        json={"question": "客户问刹车片有没有噪音，怎么回复？"},
    )

    assert response.status_code == 502
    assert "AI provider request failed" in response.json()["detail"]


def test_qa_ask_uses_conversation_history_for_follow_up(client, monkeypatch):
    captured_context = {}

    def fake_provider(question, context, provider=None):
        captured_context.update(context)
        return SalesAnswer(
            reply_thinking="used conversation history",
            standard_reply="English customer reply",
            references=[],
            recommended_materials=[],
            warnings=[],
        )

    monkeypatch.setattr(qa_router, "generate_sales_answer", fake_provider)

    response = client.post(
        "/api/qa/ask",
        json={
            "question": "那英文怎么说？",
            "conversation_history": [
                {"role": "user", "content": "客户问刹车片有没有噪音，怎么回复？"},
                {"role": "assistant", "content": "可以说明正常安装后噪音控制稳定。"},
            ],
        },
    )

    assert response.status_code == 200
    agent_plan = captured_context["agent_plan"]
    assert agent_plan["is_follow_up"] is True
    assert agent_plan["language"] == "en"
    assert agent_plan["effective_question"] == "客户问刹车片有没有噪音，怎么回复？ 那英文怎么说？"


def test_qa_ask_uses_distribution_runtime_provider(client, monkeypatch):
    captured_distribution_ids = []

    class RuntimeProvider:
        def generate(self, question, context):
            return SalesAnswer(
                reply_thinking="runtime provider",
                standard_reply=f"runtime reply for {question}",
                references=[],
                recommended_materials=[],
                warnings=[],
            )

    def fake_provider_from_distribution(distribution_id):
        captured_distribution_ids.append(distribution_id)
        return RuntimeProvider()

    monkeypatch.setattr(
        qa_router,
        "provider_from_distribution",
        fake_provider_from_distribution,
    )

    response = client.post(
        "/api/qa/ask",
        json={"question": "客户问价格怎么回复？", "distribution_id": "dist_123"},
    )

    assert response.status_code == 200
    assert captured_distribution_ids == ["dist_123"]
    assert response.json()["standard_reply"] == "runtime reply for 客户问价格怎么回复？"


def test_qa_ask_builds_order_comparison_context_for_compare_question(client, monkeypatch):
    seed_acceptance_price_history()
    captured_context = {}

    def fake_provider(question, context, provider=None):
        captured_context.update(context)
        return SalesAnswer(
            reply_thinking="order comparison used",
            standard_reply="已对比历史订单。",
            references=[],
            recommended_materials=[],
            warnings=[],
        )

    monkeypatch.setattr(qa_router, "generate_sales_answer", fake_provider)

    response = client.post(
        "/api/qa/ask",
        json={"question": "Ahmed 这次要 D1234 和 D5678，帮我和上次订单比一下。"},
    )

    assert response.status_code == 200
    order_comparison = captured_context["order_comparison"]
    statuses = {item["part_number"]: item["status"] for item in order_comparison["items"]}
    assert statuses == {"D1234": "historical_part", "D5678": "new_part"}
    assert "订单比对库" in captured_context["agent_plan"]["required_actions"]


def test_runtime_distribution_proxy_hides_api_key(client, monkeypatch):
    def fake_runtime_config(distribution_id):
        assert distribution_id == "dist_123"
        return {
            "distributionId": "dist_123",
            "status": "enabled",
            "app": {"name": "分发应用", "url": "http://example.test/qa"},
            "model": {
                "provider": "openai",
                "model": "gpt-5.5",
                "apiBaseUrl": "https://token-gpt.top/v1",
                "apiKey": "sk-secret",
                "enabled": True,
                "parameters": {"temperature": 0.2},
            },
        }

    monkeypatch.setattr(qa_router, "fetch_runtime_distribution_config", fake_runtime_config)

    response = client.get("/api/runtime/distributions/dist_123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"]["name"] == "分发应用"
    assert payload["model"]["parameters"] == {"temperature": 0.2}
    assert "apiKey" not in payload["model"]
    assert "sk-secret" not in response.text


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


def test_qa_ask_returns_openable_material_file_url(client, tmp_path):
    image_path = tmp_path / "hiq-packaging.jpg"
    image_path.write_bytes(b"fake image bytes")
    with database.SessionLocal() as db:
        material = create_material(
            db,
            {
                "name": "HIQ 包装图片",
                "file_path": str(image_path),
                "material_type": "image",
                "product_type": "brake_pad",
                "scenario": "包装效果",
                "brand": "HIQ",
                "description": "HIQ 彩盒包装图片，可发给客户确认包装风格。",
                "recommended_script": "这是 HIQ 彩盒包装图片，可以给客户展示包装细节。",
                "tags": "包装,HIQ,图片",
            },
        )

    qa_response = client.post(
        "/api/qa/ask",
        json={"question": "客户想看 HIQ 包装图片，怎么回复？"},
    )

    assert qa_response.status_code == 200
    material_payload = qa_response.json()["recommended_materials"][0]
    assert material_payload["id"] == material["id"]
    assert material_payload["file_url"] == f"/api/materials/{material['id']}/file"

    file_response = client.get(material_payload["file_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"fake image bytes"


def test_qa_ask_material_question_mentions_sending_matched_material(client, tmp_path):
    video_path = tmp_path / "hiq-packaging.mp4"
    video_path.write_bytes(b"fake video bytes")
    with database.SessionLocal() as db:
        create_material(
            db,
            {
                "name": "HIQ 包装视频",
                "file_path": str(video_path),
                "material_type": "video",
                "product_type": "brake_pad",
                "scenario": "包装效果",
                "brand": "HIQ",
                "description": "HIQ 彩盒包装视频，可发给客户查看包装风格。",
                "recommended_script": "这是 HIQ 包装实拍视频。",
                "tags": "包装,HIQ,视频",
            },
        )

    response = client.post(
        "/api/qa/ask",
        json={"question": "客户想看 HIQ 包装视频，怎么回复？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_materials"]
    assert "素材" in payload["standard_reply"] or "视频" in payload["standard_reply"]
    assert "HIQ" in payload["standard_reply"]


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


def test_acceptance_case_6_agent_material_recommendation_with_english_reply(client):
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

    response = client.post(
        "/api/qa/ask",
        json={"question": "客户想看 HIQ 包装视频，顺便用英文回复他。"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "HIQ" in payload["standard_reply"]
    assert "send" in payload["standard_reply"].lower()
    assert payload["recommended_materials"]
    assert payload["recommended_materials"][0]["brand"] == "HIQ"


def test_acceptance_case_7_quote_question_asks_for_missing_information(client):
    response = client.post(
        "/api/qa/ask",
        json={"question": "客户要报价，怎么回复？"},
    )

    assert response.status_code == 200
    reply = response.json()["standard_reply"]
    assert "型号" in reply
    assert "数量" in reply
    assert "包装" in reply
    assert "目的港" in reply or "国家" in reply
    assert "随机价格" not in reply
