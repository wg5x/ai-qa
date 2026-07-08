from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SpeechTemplate, utc_now


EDITABLE_FIELDS = {
    "scenario",
    "customer_question",
    "style_notes",
    "standard_reply",
    "forbidden_words",
    "recommended_material_ids",
}

CONTENT_FIELDS = EDITABLE_FIELDS


class InvalidTemplateTransitionError(ValueError):
    pass


def summarize_chat_to_template(db: Session, source_chat: str) -> dict[str, Any]:
    template = SpeechTemplate(
        **_fake_summarize_chat(source_chat),
        source_chat=source_chat,
        status="draft",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return serialize_template(template)


def list_templates(db: Session) -> list[dict[str, Any]]:
    templates = db.scalars(select(SpeechTemplate).order_by(SpeechTemplate.id.desc()))
    return [serialize_template(template) for template in templates]


def update_template(
    db: Session, template_id: int, data: dict[str, Any]
) -> dict[str, Any] | None:
    template = db.get(SpeechTemplate, template_id)
    if template is None:
        return None

    content_changed = False
    for key, value in data.items():
        if key not in EDITABLE_FIELDS:
            continue
        if key in CONTENT_FIELDS and getattr(template, key) != value:
            content_changed = True
        setattr(template, key, value)
    if template.status == "confirmed" and content_changed:
        template.status = "draft"
        template.confirmed_at = None
    db.commit()
    db.refresh(template)
    return serialize_template(template)


def confirm_template(db: Session, template_id: int) -> dict[str, Any] | None:
    template = db.get(SpeechTemplate, template_id)
    if template is None:
        return None
    if template.status != "draft":
        raise InvalidTemplateTransitionError("Only draft templates can be confirmed")

    template.status = "confirmed"
    template.confirmed_at = utc_now()
    db.commit()
    db.refresh(template)
    return serialize_template(template)


def disable_template(db: Session, template_id: int) -> dict[str, Any] | None:
    template = db.get(SpeechTemplate, template_id)
    if template is None:
        return None
    if template.status == "disabled":
        raise InvalidTemplateTransitionError("Template is already disabled")

    template.status = "disabled"
    db.commit()
    db.refresh(template)
    return serialize_template(template)


def _fake_summarize_chat(source_chat: str) -> dict[str, str]:
    if any(keyword in source_chat for keyword in ("噪音", "异响", "静音")):
        return {
            "scenario": "noise_reply",
            "customer_question": "客户问刹车片有没有噪音。",
            "style_notes": "专业、简洁，先说明稳定性再建议检查安装。",
            "standard_reply": "我们的刹车片正常安装后噪音控制稳定，如有异响可协助检查安装和磨合情况。",
            "forbidden_words": "绝对静音, 永不异响",
            "recommended_material_ids": "",
        }
    if "包装" in source_chat or "package" in source_chat.lower():
        return {
            "scenario": "packaging_reply",
            "customer_question": "客户问包装怎么展示。",
            "style_notes": "简洁说明包装卖点，并推荐可发送素材。",
            "standard_reply": "可以发送包装视频，并说明彩盒细节。",
            "forbidden_words": "保证一模一样",
            "recommended_material_ids": "",
        }
    return {
        "scenario": "general_reply",
        "customer_question": "客户提出常见销售问题。",
        "style_notes": "友好、准确，避免承诺未经确认的信息。",
        "standard_reply": "我们会结合现有资料确认后给您准确回复。",
        "forbidden_words": "最低价, 保证",
        "recommended_material_ids": "",
    }


def serialize_template(template: SpeechTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "scenario": template.scenario,
        "customer_question": template.customer_question,
        "style_notes": template.style_notes,
        "standard_reply": template.standard_reply,
        "forbidden_words": template.forbidden_words,
        "recommended_material_ids": template.recommended_material_ids,
        "status": template.status,
        "source_chat": template.source_chat,
        "created_at": _serialize_datetime(template.created_at),
        "confirmed_at": _serialize_datetime(template.confirmed_at),
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
