import json
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContractRecord, Material, QuoteRecord, SpeechTemplate
from app.services.material_search import is_low_confidence_material
from app.services.order_compare import compare_order_items
from app.services.quote_search import search_historical_prices


SAFETY_RULES = [
    "标准回复不得包含报价公式。",
    "标准回复不得包含供应商成本、底价或利润空间。",
    "只使用与当前客户和型号直接相关的记录，不上传其他客户完整数据。",
]

COMMON_CUSTOMER_WORDS = {
    "auto",
    "automotive",
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "import",
    "export",
    "international",
    "llc",
    "ltd",
    "limited",
    "motors",
    "parts",
    "trading",
    "trade",
}

COMMON_BRAND_WORDS = COMMON_CUSTOMER_WORDS | {
    "box",
    "brake",
    "brand",
    "document",
    "image",
    "material",
    "package",
    "packaging",
    "pad",
    "pads",
    "photo",
    "photos",
    "private",
    "video",
}

MATERIAL_SCENARIO_KEYWORDS = {
    "packaging",
    "package",
    "price",
    "quote",
    "quality",
    "noise",
    "factory",
    "certificate",
    "installation",
    "box",
    "报价",
    "价格",
    "包装",
    "质量",
    "噪音",
    "异响",
    "静音",
    "工厂",
    "证书",
    "安装",
}

MATERIAL_SCENARIO_ALIASES = {
    "packaging": {"box", "package", "packaging", "包装"},
    "price": {"price", "quote", "报价", "价格"},
    "quality": {"quality", "质量"},
    "noise": {"noise", "噪音", "异响", "静音"},
    "factory": {"factory", "工厂"},
    "certificate": {"certificate", "证书"},
    "installation": {"installation", "安装"},
}
MAX_RELEVANT_TEMPLATES = 3


def build_sales_prompt_context(
    db: Session,
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    effective_question, is_follow_up = _resolve_effective_question(
        question, conversation_history or []
    )
    preliminary_intents = _detect_intents(effective_question)
    customer_name = _extract_customer_name(db, effective_question)
    part_number = _extract_part_number(db, effective_question)
    order_part_numbers = (
        _extract_order_part_numbers(db, effective_question)
        if "order_compare" in preliminary_intents
        else []
    )
    brand = _extract_material_brand(db, effective_question)
    has_price_lookup_scope = bool(customer_name and part_number)
    has_order_compare_scope = bool(customer_name and order_part_numbers)
    scoped_customer_name = customer_name if has_price_lookup_scope or has_order_compare_scope else None
    price_history = _find_price_history(db, customer_name, part_number)
    order_comparison = _find_order_comparison(
        db,
        customer_name=scoped_customer_name if has_order_compare_scope else None,
        part_numbers=order_part_numbers,
    )
    materials = _find_relevant_materials(db, effective_question)
    speech_templates = _find_relevant_confirmed_templates(db, effective_question)
    agent_plan = _build_agent_plan(
        effective_question=effective_question,
        is_follow_up=is_follow_up,
        customer_name=scoped_customer_name,
        part_number=part_number,
        brand=brand,
        price_history=price_history,
        order_comparison=order_comparison,
        materials=materials,
        speech_templates=speech_templates,
    )

    return {
        "question": question,
        "effective_question": effective_question,
        "extracted_entities": {
            "customer_name": scoped_customer_name,
            "part_number": part_number,
            "order_part_numbers": order_part_numbers,
            "brand": brand,
        },
        "price_history": price_history,
        "order_comparison": order_comparison,
        "materials": materials,
        "speech_templates": speech_templates,
        "agent_plan": agent_plan,
        "safety_rules": SAFETY_RULES,
    }


def render_sales_prompt(context: dict[str, Any]) -> str:
    return "\n".join(
        [
            "你是销售助手，请基于最小必要上下文生成回复。",
            "必须按照 agent_plan 的意图、缺失信息、工具使用结果和语言要求生成回答。",
            "上下文:",
            json.dumps(context, ensure_ascii=False, default=str, indent=2),
        ]
    )


def _resolve_effective_question(
    question: str, conversation_history: list[dict[str, str]]
) -> tuple[str, bool]:
    current_question = question.strip()
    if not _is_follow_up_question(current_question):
        return current_question, False

    previous_user_question = _last_user_question(conversation_history)
    if not previous_user_question:
        return current_question, False
    return f"{previous_user_question} {current_question}", True


def _is_follow_up_question(question: str) -> bool:
    normalized = _normalize_text(question)
    return any(
        marker in normalized
        for marker in (
            "那英文",
            "英文怎么说",
            "翻译成英文",
            "用英文",
            "那怎么说",
            "改成英文",
            "english",
            "translate",
        )
    )


def _last_user_question(conversation_history: list[dict[str, str]]) -> str | None:
    for message in reversed(conversation_history[-8:]):
        if message.get("role") == "user" and message.get("content", "").strip():
            return message["content"].strip()
    return None


def _build_agent_plan(
    *,
    effective_question: str,
    is_follow_up: bool,
    customer_name: str | None,
    part_number: str | None,
    brand: str | None,
    price_history: dict[str, object],
    order_comparison: dict[str, object],
    materials: list[dict[str, Any]],
    speech_templates: list[dict[str, Any]],
) -> dict[str, Any]:
    intents = _detect_intents(effective_question)
    missing_fields = _missing_fields_for_question(
        effective_question,
        intents,
        customer_name=customer_name,
        part_number=part_number,
    )
    if missing_fields and "missing_information" not in intents:
        insert_at = 1 if "price_lookup" in intents else len(intents)
        intents.insert(insert_at, "missing_information")

    instructions = _agent_instructions(
        intents,
        language=_detect_language(effective_question),
        is_follow_up=is_follow_up,
    )
    return {
        "intents": intents,
        "language": _detect_language(effective_question),
        "is_follow_up": is_follow_up,
        "effective_question": effective_question,
        "extracted_entities": {
            "customer_name": customer_name,
            "part_number": part_number,
            "brand": brand,
        },
        "missing_fields": missing_fields,
        "required_actions": _required_actions(intents),
        "tool_usage": {
            "price_history": _price_history_usage(price_history, intents),
            "order_comparison": _order_comparison_usage(order_comparison, intents),
            "materials": "matched"
            if materials
            else ("not_found" if "material_recommendation" in intents else "skipped"),
            "speech_templates": "matched"
            if speech_templates
            else ("not_found" if "template_reference" in intents or "customer_reply" in intents else "skipped"),
        },
        "instructions": instructions,
    }


def _detect_intents(question: str) -> list[str]:
    normalized = _normalize_text(question)
    intents: list[str] = []

    if _contains_any(
        normalized,
        ("报价", "价格", "单价", "多少钱", "price", "quote", "offer"),
    ):
        intents.append("price_lookup")
    if _contains_any(
        normalized,
        ("上次订单", "历史订单", "订单比", "对比", "比一下", "compare", "last order"),
    ):
        intents.append("order_compare")
    if _contains_any(
        normalized,
        (
            "素材",
            "视频",
            "图片",
            "照片",
            "包装",
            "看",
            "material",
            "video",
            "photo",
            "image",
            "packaging",
            "package",
            "show",
            "send",
        ),
    ):
        intents.append("material_recommendation")
    if _contains_any(
        normalized,
        ("话术", "标准回复", "模板", "standard reply", "template"),
    ):
        intents.append("template_reference")
    if _contains_any(
        normalized,
        ("怎么回复", "回复", "怎么说", "用英文", "英文怎么说", "reply", "respond"),
    ):
        intents.append("customer_reply")

    if not intents:
        intents.append("customer_reply")
    return intents


def _detect_language(question: str) -> str:
    normalized = _normalize_text(question)
    if _contains_any(normalized, ("英文", "英语", "english", "用英文", "translate")):
        return "en"
    return "zh"


def _missing_fields_for_question(
    question: str,
    intents: list[str],
    *,
    customer_name: str | None,
    part_number: str | None,
) -> list[str]:
    if "price_lookup" not in intents:
        return []

    normalized = _normalize_text(question)
    if _is_historical_lookup(normalized):
        missing = []
        if not customer_name:
            missing.append("客户名称")
        if not part_number:
            missing.append("型号/OE号")
        return missing

    missing = []
    if not part_number:
        missing.append("型号/OE号")
    if not re.search(r"\d+", normalized):
        missing.append("数量")
    if not _contains_any(normalized, ("包装", "彩盒", "中性", "品牌包装", "package", "box")):
        missing.append("包装要求")
    if not _contains_any(normalized, ("目的港", "国家", "市场", "港", "港口", "country", "port")):
        missing.append("目的港/国家")
    if not _contains_any(normalized, ("fob", "cif", "exw", "贸易条款", "条款", "terms")):
        missing.append("贸易条款")
    return missing


def _is_historical_lookup(normalized_question: str) -> bool:
    return _contains_any(
        normalized_question,
        ("之前", "历史", "上次", "买过", "查一下", "previous", "history", "last"),
    )


def _required_actions(intents: list[str]) -> list[str]:
    actions = []
    if "price_lookup" in intents:
        actions.append("报价/合同库")
    if "order_compare" in intents:
        actions.append("订单比对库")
    if "material_recommendation" in intents:
        actions.append("素材库")
    if "template_reference" in intents or "customer_reply" in intents:
        actions.append("已确认话术模板")
    if "missing_information" in intents:
        actions.append("先追问业务员或客户补充信息")
    if "customer_reply" in intents:
        actions.append("生成客户可复制回复")
    return actions


def _agent_instructions(
    intents: list[str], *, language: str, is_follow_up: bool
) -> list[str]:
    instructions = [
        "先检索本地资料，再生成回答。",
        "参考依据必须说明使用了哪些资料类型。",
    ]
    if is_follow_up:
        instructions.append("多轮上下文：沿用上一轮业务场景，不要求业务员重复完整背景。")
    if language == "en":
        instructions.append("必须直接生成英文客户回复。")
    if "missing_information" in intents:
        instructions.append("不要生成随机价格。")
        instructions.append("先追问业务员或客户补充信息。")
    if "material_recommendation" in intents:
        instructions.append("没有匹配素材时，不推荐无关品牌素材。")
    if "template_reference" in intents or "customer_reply" in intents:
        instructions.append("只能引用已确认话术模板。")
    return instructions


def _price_history_usage(price_history: dict[str, object], intents: list[str]) -> str:
    if "price_lookup" not in intents and "order_compare" not in intents:
        return "skipped"
    if price_history.get("found") is True:
        return "matched"
    if price_history.get("message") == "请输入客户名称和型号":
        return "missing_scope"
    return "not_found"


def _order_comparison_usage(order_comparison: dict[str, object], intents: list[str]) -> str:
    if "order_compare" not in intents:
        return "skipped"
    if order_comparison.get("items"):
        return "matched"
    if order_comparison.get("message") == "请输入客户名称和型号":
        return "missing_scope"
    return "not_found"


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _find_price_history(
    db: Session, customer_name: str | None, part_number: str | None
) -> dict[str, object]:
    if not customer_name or not part_number:
        return {"found": False, "message": "请输入客户名称和型号", "quotes": [], "contracts": []}
    return search_historical_prices(db, customer_name=customer_name, part_number=part_number)


def _extract_customer_name(db: Session, question: str) -> str | None:
    question_tokens = set(_word_tokens(question))
    normalized_question = f" {' '.join(_word_tokens(question))} "
    customer_names = {
        name
        for name in db.scalars(select(QuoteRecord.customer_name))
        if name
    } | {
        name
        for name in db.scalars(select(ContractRecord.customer_name))
        if name
    }

    for name in sorted(customer_names, key=len, reverse=True):
        name_tokens = _word_tokens(name)
        if _contains_token_phrase(normalized_question, name_tokens):
            return name
        alias_tokens = [
            token
            for token in name_tokens
            if token not in COMMON_CUSTOMER_WORDS and len(token) >= 3
        ]
        if any(token in question_tokens for token in alias_tokens):
            return name
    return None


def _extract_part_number(db: Session, question: str) -> str | None:
    normalized_question = _normalize_text(question)
    part_numbers = {
        part
        for part in db.scalars(select(QuoteRecord.part_number))
        if part
    } | {
        part
        for part in db.scalars(select(ContractRecord.part_number))
        if part
    }

    for part_number in sorted(part_numbers, key=len, reverse=True):
        if _contains_part_number(normalized_question, part_number):
            return part_number
    return None


def _extract_order_part_numbers(db: Session, question: str) -> list[str]:
    normalized_question = _normalize_text(question)
    known_parts = {
        part
        for part in db.scalars(select(QuoteRecord.part_number))
        if part and _contains_part_number(normalized_question, part)
    } | {
        part
        for part in db.scalars(select(ContractRecord.part_number))
        if part and _contains_part_number(normalized_question, part)
    }
    extracted = list(sorted(known_parts, key=lambda value: normalized_question.find(_normalize_text(value))))
    for match in re.findall(r"(?<![a-z0-9])([a-z]{1,6}-?\d{2,8}[a-z0-9-]*)(?![a-z0-9])", normalized_question):
        normalized_match = match.upper()
        if normalized_match not in extracted:
            extracted.append(normalized_match)
    return extracted


def _find_order_comparison(
    db: Session,
    *,
    customer_name: str | None,
    part_numbers: list[str],
) -> dict[str, object]:
    if not customer_name or not part_numbers:
        return {"found": False, "message": "请输入客户名称和型号", "items": []}
    result = compare_order_items(
        db,
        customer_name=customer_name,
        items=[{"part_number": part_number} for part_number in part_numbers],
    )
    return {"found": True, **result}


def _extract_material_brand(db: Session, question: str) -> str | None:
    question_tokens = set(_word_tokens(question))
    normalized_question = f" {' '.join(_word_tokens(question))} "
    brands = {
        brand
        for brand in db.scalars(select(Material.brand))
        if brand
    }

    for brand in sorted(brands, key=len, reverse=True):
        brand_tokens = _word_tokens(brand)
        if _brand_matches_question(brand_tokens, question_tokens, normalized_question):
            return brand
    return None


def _find_relevant_materials(db: Session, question: str) -> list[dict[str, Any]]:
    question_tokens = set(_word_tokens(question))
    normalized_question = f" {' '.join(_word_tokens(question))} "
    materials = db.scalars(select(Material).order_by(Material.id.desc()))
    matched = [
        _serialize_material_summary(material)
        for material in materials
        if _material_matches_question(material, question_tokens, normalized_question)
        and not is_low_confidence_material(material)
    ]
    if matched:
        return matched

    return [
        _serialize_material_summary(material)
        for material in materials
        if _material_matches_question(material, question_tokens, normalized_question)
    ][:1]


def _material_matches_question(
    material: Material, question_tokens: set[str], normalized_question: str
) -> bool:
    brand_tokens = _word_tokens(material.brand)
    if not _brand_matches_question(brand_tokens, question_tokens, normalized_question):
        return False

    material_scenario_tokens = set(
        _word_tokens(" ".join([material.name or "", material.scenario or "", material.tags or ""]))
    )
    requested_scenarios = _scenario_categories(question_tokens)
    material_scenarios = _scenario_categories(material_scenario_tokens)
    return bool(requested_scenarios.intersection(material_scenarios))


def _brand_matches_question(
    brand_tokens: list[str], question_tokens: set[str], normalized_question: str
) -> bool:
    if not brand_tokens:
        return False
    if _contains_token_phrase(normalized_question, brand_tokens):
        return True
    explicit_brand_tokens = {
        token for token in brand_tokens if token not in COMMON_BRAND_WORDS and len(token) >= 3
    }
    return bool(explicit_brand_tokens.intersection(question_tokens))


def _scenario_categories(tokens: set[str]) -> set[str]:
    return {
        category
        for category, aliases in MATERIAL_SCENARIO_ALIASES.items()
        if aliases.intersection(tokens)
    }


def _contains_token_phrase(normalized_question: str, phrase_tokens: list[str]) -> bool:
    if not phrase_tokens:
        return False
    return f" {' '.join(phrase_tokens)} " in normalized_question


def _contains_part_number(normalized_question: str, part_number: str) -> bool:
    normalized_part = re.escape(_normalize_text(part_number))
    return re.search(rf"(?<![a-z0-9]){normalized_part}(?![a-z0-9])", normalized_question) is not None


def _word_tokens(value: str | None) -> list[str]:
    normalized = _normalize_text(value)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized)
        if len(token) >= 2
    ]
    tokens.extend(
        keyword
        for keyword in MATERIAL_SCENARIO_KEYWORDS
        if any("\u4e00" <= char <= "\u9fff" for char in keyword)
        and keyword in normalized
        and keyword not in tokens
    )
    return tokens


def _normalize_text(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").lower()


def _serialize_material_summary(material: Material) -> dict[str, Any]:
    return {
        "id": material.id,
        "name": material.name,
        "file_path": material.file_path,
        "material_type": material.material_type,
        "scenario": material.scenario,
        "brand": material.brand,
        "description": material.description,
        "recommended_script": material.recommended_script,
        "tags": material.tags,
        "file_url": f"/api/materials/{material.id}/file" if material.id else None,
    }


def _find_relevant_confirmed_templates(db: Session, question: str) -> list[dict[str, Any]]:
    question_scenarios = _scenario_categories(set(_word_tokens(question)))
    if not question_scenarios:
        return []

    templates = db.scalars(
        select(SpeechTemplate)
        .where(SpeechTemplate.status == "confirmed")
        .order_by(SpeechTemplate.confirmed_at.desc(), SpeechTemplate.id.desc())
    )
    return [
        _serialize_template(template)
        for template in templates
        if _template_matches_question(template, question_scenarios)
    ][:MAX_RELEVANT_TEMPLATES]


def _template_matches_question(
    template: SpeechTemplate, question_scenarios: set[str]
) -> bool:
    template_text = " ".join(
        [
            template.scenario or "",
            template.customer_question or "",
            template.style_notes or "",
            template.standard_reply or "",
        ]
    )
    template_scenarios = _scenario_categories(set(_word_tokens(template_text)))
    return bool(question_scenarios.intersection(template_scenarios))


def _serialize_template(template: SpeechTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "scenario": template.scenario,
        "customer_question": template.customer_question,
        "style_notes": template.style_notes,
        "standard_reply": template.standard_reply,
        "forbidden_words": template.forbidden_words,
        "recommended_material_ids": template.recommended_material_ids,
    }
