import json
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContractRecord, Material, QuoteRecord, SpeechTemplate
from app.services.material_search import is_low_confidence_material
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


def build_sales_prompt_context(db: Session, question: str) -> dict[str, Any]:
    customer_name = _extract_customer_name(db, question)
    part_number = _extract_part_number(db, question)
    has_price_lookup_scope = bool(customer_name and part_number)
    price_history = _find_price_history(db, customer_name, part_number)

    return {
        "question": question,
        "extracted_entities": {
            "customer_name": customer_name if has_price_lookup_scope else None,
            "part_number": part_number if has_price_lookup_scope else None,
        },
        "price_history": price_history,
        "materials": _find_relevant_materials(db, question),
        "speech_templates": _find_relevant_confirmed_templates(db, question),
        "safety_rules": SAFETY_RULES,
    }


def render_sales_prompt(context: dict[str, Any]) -> str:
    return "\n".join(
        [
            "你是销售助手，请基于最小必要上下文生成回复。",
            "上下文:",
            json.dumps(context, ensure_ascii=False, default=str, indent=2),
        ]
    )


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
