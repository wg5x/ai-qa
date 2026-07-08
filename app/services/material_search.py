import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material


QUERY_KEYWORDS = ("包装", "材质", "工厂", "品牌", "证书", "安装", "刹车片")
LOW_CONFIDENCE_TAG = "needs_description"


def is_low_confidence_material(material: Material | dict[str, Any]) -> bool:
    tags = material.tags if isinstance(material, Material) else material.get("tags")
    return _contains(tags, LOW_CONFIDENCE_TAG)


def create_material(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    material = Material(**_clean_payload(data))
    db.add(material)
    db.commit()
    db.refresh(material)
    return _serialize_material(material)


def list_materials(db: Session) -> list[dict[str, Any]]:
    materials = db.scalars(select(Material).order_by(Material.id.desc()))
    return [_serialize_material(material) for material in materials]


def search_materials(
    db: Session,
    query: str | None = None,
    scenario: str | None = None,
    tags: str | None = None,
    brand: str | None = None,
    material_grade: str | None = None,
) -> list[dict[str, Any]]:
    materials = list(db.scalars(select(Material).order_by(Material.id.desc())))
    filters = {
        "scenario": scenario,
        "tags": tags,
        "brand": brand,
        "material_grade": material_grade,
    }

    results = []
    for material in materials:
        if not _matches_filters(material, filters):
            continue
        if query and not _matches_query(material, query):
            continue
        results.append(material)

    results.sort(key=lambda material: (is_low_confidence_material(material), -(material.id or 0)))
    return [_serialize_material(material) for material in results]


def update_material(
    db: Session, material_id: int, data: dict[str, Any]
) -> dict[str, Any] | None:
    material = db.get(Material, material_id)
    if material is None:
        return None

    for key, value in _clean_payload(data).items():
        setattr(material, key, value)
    db.commit()
    db.refresh(material)
    return _serialize_material(material)


def delete_material(db: Session, material_id: int) -> bool:
    material = db.get(Material, material_id)
    if material is None:
        return False

    db.delete(material)
    db.commit()
    return True


def _clean_payload(data: dict[str, Any]) -> dict[str, Any]:
    valid_fields = {
        "name",
        "file_path",
        "material_type",
        "product_type",
        "scenario",
        "brand",
        "material_grade",
        "description",
        "recommended_script",
        "tags",
    }
    return {key: value for key, value in data.items() if key in valid_fields}


def _matches_filters(material: Material, filters: dict[str, str | None]) -> bool:
    for field_name, expected in filters.items():
        if expected and not _contains(getattr(material, field_name), expected):
            return False
    return True


def _matches_query(material: Material, query: str) -> bool:
    fields = _searchable_values(material)
    signals = _query_signals(query)
    if signals:
        return all(_signal_matches(signal, fields) for signal in signals)

    normalized_query = _normalize(query)
    return bool(normalized_query) and any(
        normalized_query in field or field in normalized_query for field in fields
    )


def _query_signals(query: str) -> list[str]:
    normalized_query = _normalize(query)
    signals = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized_query)
        if len(token) >= 2
    ]
    signals.extend(keyword for keyword in QUERY_KEYWORDS if keyword in query)
    return list(dict.fromkeys(signals))


def _signal_matches(signal: str, fields: list[str]) -> bool:
    return any(signal in field or field in signal for field in fields)


def _searchable_values(material: Material) -> list[str]:
    values = [
        material.name,
        material.file_path,
        material.material_type,
        material.product_type,
        material.scenario,
        material.brand,
        material.material_grade,
        material.description,
        material.recommended_script,
        material.tags,
    ]
    chunks: list[str] = []
    for value in values:
        if value is None:
            continue
        normalized = _normalize(value)
        if normalized:
            chunks.append(normalized)
        chunks.extend(
            chunk
            for chunk in re.split(r"[,;，；、/\s]+", normalized)
            if len(chunk) >= 2
        )
    return chunks


def _contains(value: str | None, expected: str) -> bool:
    return _normalize(expected) in _normalize(value)


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _serialize_material(material: Material) -> dict[str, Any]:
    return {
        "id": material.id,
        "name": material.name,
        "file_path": material.file_path,
        "material_type": material.material_type,
        "product_type": material.product_type,
        "scenario": material.scenario,
        "brand": material.brand,
        "material_grade": material.material_grade,
        "description": material.description,
        "recommended_script": material.recommended_script,
        "tags": material.tags,
        "created_at": _serialize_datetime(material.created_at),
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
