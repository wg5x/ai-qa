from app import database
from app.services.prompt_builder import build_sales_prompt_context, render_sales_prompt


def _template_replies(question: str) -> list[str]:
    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, question)
    return [template["standard_reply"] for template in context["speech_templates"]]


def test_summarize_chat_creates_draft_template_excluded_from_prompt_context(client):
    response = client.post(
        "/api/templates/summarize",
        json={
            "source_chat": (
                "客户问刹车片有没有噪音。销售回复：正常安装后噪音控制稳定，"
                "如有异响可先检查安装和磨合情况。"
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["scenario"] == "noise_reply"
    assert payload["customer_question"] == "客户问刹车片有没有噪音。"
    assert payload["style_notes"] == "专业、简洁，先说明稳定性再建议检查安装。"
    assert payload["standard_reply"] == "我们的刹车片正常安装后噪音控制稳定，如有异响可协助检查安装和磨合情况。"
    assert payload["forbidden_words"] == "绝对静音, 永不异响"
    assert payload["recommended_material_ids"] == ""
    assert payload["source_chat"]
    assert payload["confirmed_at"] is None

    with database.SessionLocal() as db:
        context = build_sales_prompt_context(db, "客户问刹车片有没有噪音，怎么回复？")

    assert context["speech_templates"] == []
    assert "噪音控制稳定" not in render_sales_prompt(context)


def test_confirming_draft_template_allows_prompt_builder_to_use_it(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()

    response = client.post(f"/api/templates/{draft['id']}/confirm")

    assert response.status_code == 200
    confirmed = response.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_at"] is not None
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == [
        "我们的刹车片正常安装后噪音控制稳定，如有异响可协助检查安装和磨合情况。"
    ]


def test_disabling_confirmed_template_removes_it_from_prompt_context(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()
    client.post(f"/api/templates/{draft['id']}/confirm")

    response = client.post(f"/api/templates/{draft['id']}/disable")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == []


def test_list_and_patch_templates(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问包装怎么展示。销售回复：发送包装视频。"},
    ).json()

    patch_response = client.patch(
        f"/api/templates/{draft['id']}",
        json={
            "scenario": "packaging_reply",
            "standard_reply": "可以发送包装视频，并说明彩盒细节。",
        },
    )
    list_response = client.get("/api/templates")

    assert patch_response.status_code == 200
    assert patch_response.json()["scenario"] == "packaging_reply"
    assert patch_response.json()["standard_reply"] == "可以发送包装视频，并说明彩盒细节。"
    assert list_response.status_code == 200
    assert [template["id"] for template in list_response.json()] == [draft["id"]]


def test_template_endpoints_return_404_for_unknown_id(client):
    assert client.patch("/api/templates/9999", json={"scenario": "noise_reply"}).status_code == 404
    assert client.post("/api/templates/9999/confirm").status_code == 404
    assert client.post("/api/templates/9999/disable").status_code == 404


def test_confirm_and_disable_reject_invalid_state_transitions(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()

    assert client.post(f"/api/templates/{draft['id']}/disable").status_code == 200
    assert client.post(f"/api/templates/{draft['id']}/confirm").status_code == 409
    assert client.post(f"/api/templates/{draft['id']}/disable").status_code == 409


def test_editing_confirmed_content_returns_template_to_draft_until_reconfirmed(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()
    confirmed = client.post(f"/api/templates/{draft['id']}/confirm").json()

    response = client.patch(
        f"/api/templates/{confirmed['id']}",
        json={"standard_reply": "新版噪音回复：先确认安装，再说明噪音控制稳定。"},
    )

    assert response.status_code == 200
    edited = response.json()
    assert edited["status"] == "draft"
    assert edited["confirmed_at"] is None
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == []

    reconfirmed = client.post(f"/api/templates/{edited['id']}/confirm").json()

    assert reconfirmed["status"] == "confirmed"
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == [
        "新版噪音回复：先确认安装，再说明噪音控制稳定。"
    ]


def test_editing_disabled_template_keeps_it_disabled_and_excluded(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()
    client.post(f"/api/templates/{draft['id']}/confirm")
    disabled = client.post(f"/api/templates/{draft['id']}/disable").json()

    response = client.patch(
        f"/api/templates/{disabled['id']}",
        json={"standard_reply": "禁用模板即使编辑也不能进入上下文。"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == []


def test_patch_cannot_directly_change_status_confirmation_or_source_chat(client):
    draft = client.post(
        "/api/templates/summarize",
        json={"source_chat": "客户问刹车片有没有噪音。销售回复：噪音控制稳定。"},
    ).json()

    response = client.patch(
        f"/api/templates/{draft['id']}",
        json={
            "status": "confirmed",
            "confirmed_at": "2026-07-07T12:00:00+00:00",
            "source_chat": "tampered source chat",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["confirmed_at"] is None
    assert payload["source_chat"] == draft["source_chat"]
    assert _template_replies("客户问刹车片有没有噪音，怎么回复？") == []
