import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material
from app.services.material_search import create_material, is_low_confidence_material

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi"}
HASH_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
MATERIAL_GRADE_PATTERN = re.compile(
    r"(A\+\+?半金属|A\+\+?陶瓷|A半金属|普通半金属|AAA|AA|A\+)",
    re.IGNORECASE,
)
WECHAT_IMAGE_PATTERN = re.compile(r"^微信图片_", re.IGNORECASE)
MIN_KNOWLEDGE_PARAGRAPH_LENGTH = 12


def extract_docx_paragraphs(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    paragraphs: list[str] = []
    for paragraph_node in root.findall(".//w:p", DOCX_NS):
        texts = [
            text_node.text
            for text_node in paragraph_node.findall(".//w:t", DOCX_NS)
            if text_node.text
        ]
        paragraph = "".join(texts).strip()
        if len(paragraph) >= MIN_KNOWLEDGE_PARAGRAPH_LENGTH:
            paragraphs.append(paragraph)
    return paragraphs


def import_manual_knowledge(
    db: Session,
    docx_path: Path,
    *,
    source_label: str = "谈单手册",
) -> dict[str, Any]:
    paragraphs = extract_docx_paragraphs(docx_path)
    created = 0
    skipped = 0

    for index, paragraph in enumerate(paragraphs, start=1):
        if _manual_paragraph_exists(db, paragraph):
            skipped += 1
            continue

        create_material(
            db,
            {
                "name": _truncate(paragraph, 60),
                "file_path": str(docx_path.resolve()),
                "material_type": "knowledge",
                "product_type": "brake_pad",
                "scenario": "谈单知识",
                "description": paragraph,
                "tags": f"manual,{source_label},knowledge_fragment",
            },
        )
        created += 1

    return {
        "source_file": str(docx_path.resolve()),
        "paragraphs_found": len(paragraphs),
        "created": created,
        "skipped": skipped,
    }


def import_media_directory(
    db: Session,
    media_dir: Path,
    *,
    product_type: str = "brake_pad",
) -> dict[str, Any]:
    if not media_dir.exists():
        raise FileNotFoundError(f"素材目录不存在: {media_dir}")

    created = 0
    skipped = 0
    low_confidence = 0

    for file_path in sorted(media_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if _media_file_exists(db, file_path):
            skipped += 1
            continue

        payload = build_media_payload(file_path, product_type=product_type)
        create_material(db, payload)
        created += 1
        if is_low_confidence_material(payload):
            low_confidence += 1

    return {
        "media_dir": str(media_dir.resolve()),
        "created": created,
        "skipped": skipped,
        "low_confidence": low_confidence,
    }


def build_media_payload(file_path: Path, *, product_type: str) -> dict[str, Any]:
    stem = file_path.stem
    material_grade = _extract_material_grade(stem)
    low_confidence = _is_low_confidence_filename(stem, material_grade)
    material_type = _detect_material_type(file_path.suffix.lower())

    tags = ["auto_indexed", product_type]
    if material_grade:
        tags.append(material_grade)
    if low_confidence:
        tags.append("needs_description")

    description = (
        "自动索引素材，文件名包含业务信息，可直接用于推荐。"
        if not low_confidence
        else "自动索引素材，文件名缺少业务含义，请补充描述后再用于推荐。"
    )

    return {
        "name": stem if not low_confidence else file_path.name,
        "file_path": str(file_path.resolve()),
        "material_type": material_type,
        "product_type": product_type,
        "scenario": "材质展示" if material_grade else "待补充场景",
        "material_grade": material_grade,
        "description": description,
        "tags": ",".join(tags),
    }


def search_manual_knowledge(db: Session, query: str) -> list[dict[str, Any]]:
    materials = db.scalars(
        select(Material)
        .where(Material.material_type == "knowledge")
        .order_by(Material.id.desc())
    )
    normalized_query = query.strip().lower()
    results = []
    for material in materials:
        haystack = " ".join(
            [
                material.name or "",
                material.description or "",
                material.tags or "",
            ]
        ).lower()
        if normalized_query in haystack:
            results.append(material)
    return results


def list_manual_knowledge(db: Session) -> list[dict[str, Any]]:
    materials = db.scalars(
        select(Material)
        .where(Material.material_type == "knowledge")
        .order_by(Material.id.desc())
    )
    return [_serialize_manual_knowledge(material) for material in materials]


def _manual_paragraph_exists(db: Session, paragraph: str) -> bool:
    existing = db.scalars(
        select(Material.description).where(Material.material_type == "knowledge")
    )
    return paragraph in set(existing)


def _media_file_exists(db: Session, file_path: Path) -> bool:
    resolved = str(file_path.resolve())
    existing_paths = {
        path
        for path in db.scalars(select(Material.file_path))
        if path
    }
    return resolved in existing_paths


def _extract_material_grade(stem: str) -> str | None:
    match = MATERIAL_GRADE_PATTERN.search(stem)
    return match.group(1) if match else None


def _is_low_confidence_filename(stem: str, material_grade: str | None) -> bool:
    if material_grade:
        return False
    if HASH_FILENAME_PATTERN.match(stem):
        return True
    if WECHAT_IMAGE_PATTERN.match(stem):
        return True
    return len(stem) <= 4


def _detect_material_type(suffix: str) -> str:
    if suffix in {".mp4", ".mov", ".avi"}:
        return "video"
    return "image"


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"


def _serialize_manual_knowledge(material: Material) -> dict[str, Any]:
    return {
        "id": material.id,
        "name": material.name,
        "file_path": material.file_path,
        "material_type": material.material_type,
        "product_type": material.product_type,
        "scenario": material.scenario,
        "description": material.description,
        "tags": material.tags,
        "created_at": material.created_at.isoformat() if material.created_at else None,
    }
