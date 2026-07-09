from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Material, MaterialReviewItem, utc_now
from app.services.media_analysis import MediaAnalysis, analyze_media
from app.services.material_search import (
    create_material,
    is_low_confidence_material,
    paginate_materials,
)
from app.services.raw_material_seed import (
    build_media_payload,
)


EDITABLE_REVIEW_FIELDS = {
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

KNOWN_BRANDS = ("STOP BRAKE", "STOPBRAKE", "ASIMCO", "EMVP", "HIQ", "KD")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}


class InvalidMaterialReviewTransitionError(ValueError):
    pass


def scan_material_reviews(
    db: Session,
    directory_path: str,
    *,
    product_type: str = "brake_pad",
    recursive: bool = True,
) -> dict[str, Any]:
    root = Path(directory_path).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"素材路径不存在: {root}")

    files = _candidate_files(root, recursive=recursive)
    created = 0
    skipped = 0
    for file_path in files:
        if _review_or_material_exists(db, file_path):
            skipped += 1
            continue
        db.add(MaterialReviewItem(**analyze_material_file(file_path, product_type=product_type)))
        created += 1

    if created:
        db.commit()

    pending = db.scalar(
        select(func.count())
        .select_from(MaterialReviewItem)
        .where(MaterialReviewItem.status == "pending")
    )
    return {
        "source_path": str(root.resolve()),
        "created": created,
        "skipped": skipped,
        "pending": pending or 0,
    }


def analyze_material_path(
    file_path: str,
    *,
    product_type: str = "brake_pad",
    distribution_id: str | None = None,
) -> dict[str, Any]:
    return analyze_material_path_with_model(
        file_path,
        product_type=product_type,
        distribution_id=distribution_id,
    )


def analyze_material_path_with_model(
    file_path: str,
    *,
    product_type: str = "brake_pad",
    distribution_id: str | None = None,
) -> dict[str, Any]:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"素材文件不存在: {path}")
    if not _is_supported_media(path):
        raise FileNotFoundError(f"不支持的素材类型: {path}")
    suggestion = analyze_material_file(
        path,
        product_type=product_type,
        distribution_id=distribution_id,
    )
    suggestion.pop("source_path", None)
    suggestion.pop("status", None)
    return suggestion


def list_material_reviews(
    db: Session,
    *,
    status: str = "pending",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    query = select(MaterialReviewItem).order_by(MaterialReviewItem.id.desc())
    if status:
        query = query.where(MaterialReviewItem.status == status)
    return paginate_materials(
        [_serialize_review(item) for item in db.scalars(query)],
        page=page,
        page_size=page_size,
    )


def update_material_review(
    db: Session, review_id: int, data: dict[str, Any]
) -> dict[str, Any] | None:
    item = db.get(MaterialReviewItem, review_id)
    if item is None:
        return None
    if item.status != "pending":
        raise InvalidMaterialReviewTransitionError("Only pending material reviews can be edited")

    for key, value in data.items():
        if key in EDITABLE_REVIEW_FIELDS:
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _serialize_review(item)


def confirm_material_review(db: Session, review_id: int) -> dict[str, Any] | None:
    item = db.get(MaterialReviewItem, review_id)
    if item is None:
        return None
    if item.status != "pending":
        raise InvalidMaterialReviewTransitionError("Only pending material reviews can be confirmed")

    material = create_material(db, _review_to_material_payload(item))
    item.status = "confirmed"
    item.material_id = material["id"]
    item.reviewed_at = utc_now()
    db.commit()
    db.refresh(item)
    return _serialize_review(item)


def reject_material_review(db: Session, review_id: int) -> dict[str, Any] | None:
    item = db.get(MaterialReviewItem, review_id)
    if item is None:
        return None
    if item.status != "pending":
        raise InvalidMaterialReviewTransitionError("Only pending material reviews can be rejected")

    item.status = "rejected"
    item.reviewed_at = utc_now()
    db.commit()
    db.refresh(item)
    return _serialize_review(item)


def analyze_material_file(
    file_path: Path,
    *,
    product_type: str,
    distribution_id: str | None = None,
    analyzer=None,
) -> dict[str, Any]:
    payload = build_media_payload(file_path, product_type=product_type)
    path_text = str(file_path)
    material_type = payload["material_type"]
    analysis = (
        analyzer(file_path, material_type)
        if analyzer is not None
        else analyze_media(file_path, material_type=material_type, distribution_id=distribution_id)
    )
    brand = _extract_brand(path_text)
    scenario = _detect_scenario(path_text, payload.get("material_grade"))
    tags = _review_tags(payload, material_type, brand, scenario, analysis)

    return {
        "source_path": str(file_path.resolve()),
        "name": _review_name(file_path, payload),
        "file_path": str(file_path.resolve()),
        "material_type": material_type,
        "product_type": product_type,
        "scenario": scenario,
        "brand": brand,
        "material_grade": payload.get("material_grade"),
        "description": _description(
            file_path,
            material_type,
            brand,
            payload.get("material_grade"),
            scenario,
            analysis,
        ),
        "recommended_script": _recommended_script(material_type, brand, scenario, analysis),
        "tags": ",".join(tags),
        "status": "pending",
    }


def _candidate_files(root: Path, *, recursive: bool) -> list[Path]:
    if root.is_file():
        return [root] if _is_supported_media(root) else []
    iterator = root.rglob("*") if recursive else root.iterdir()
    return sorted(path for path in iterator if path.is_file() and _is_supported_media(path))


def _is_supported_media(file_path: Path) -> bool:
    return file_path.suffix.lower() in (IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)


def _review_or_material_exists(db: Session, file_path: Path) -> bool:
    resolved = str(file_path.resolve())
    review_exists = db.scalars(
        select(MaterialReviewItem.id).where(MaterialReviewItem.source_path == resolved)
    ).first()
    material_exists = db.scalars(
        select(Material.id).where(Material.file_path == resolved)
    ).first()
    return bool(review_exists or material_exists)


def _extract_brand(value: str) -> str | None:
    upper_value = value.upper()
    for brand in KNOWN_BRANDS:
        if brand in upper_value:
            return "STOP BRAKE" if brand == "STOPBRAKE" else brand
    return None


def _detect_scenario(value: str, material_grade: object) -> str:
    lower_value = value.lower()
    if any(token in lower_value for token in ("包装", "packaging", "package", "box", "彩盒")):
        return "包装展示"
    if any(token in lower_value for token in ("工厂", "factory")):
        return "工厂展示"
    if any(token in lower_value for token in ("证书", "certificate", "检测", "report")):
        return "检测报告"
    if any(token in lower_value for token in ("噪音", "静音", "noise")):
        return "噪音说明"
    if material_grade or any(token in lower_value for token in ("材质", "实物", "小片")):
        return "材质展示"
    return "待审核场景"


def _review_tags(
    payload: dict[str, Any],
    material_type: str,
    brand: str | None,
    scenario: str,
    analysis: MediaAnalysis,
) -> list[str]:
    tags = [
        tag.strip()
        for tag in str(payload.get("tags") or "").split(",")
        if tag.strip() and tag.strip() != "auto_indexed"
    ]
    tags.extend(["auto_tagged", material_type, f"{material_type}_analysis", scenario])
    tags.extend(analysis.tags)
    if analysis.ocr_text:
        tags.append("ocr")
    if analysis.transcript_text:
        tags.append("transcript")
    if analysis.frame_paths:
        tags.append("视频抽帧")
    if analysis.confidence:
        tags.append(f"{analysis.confidence}_confidence")
    if brand:
        tags.append(brand)
    return list(dict.fromkeys(tags))


def _review_name(file_path: Path, payload: dict[str, Any]) -> str:
    if not is_low_confidence_material(payload):
        return str(payload.get("name") or file_path.stem)
    return file_path.name


def _description(
    file_path: Path,
    material_type: str,
    brand: str | None,
    material_grade: object,
    scenario: str,
    analysis: MediaAnalysis,
) -> str:
    media_label = "视频" if material_type == "video" else "图片"
    parts = [f"自动分析{media_label}素材，场景初判为{scenario}。"]
    if analysis.visual_summary:
        parts.append(f"模型视觉识别：{analysis.visual_summary}")
    if analysis.ocr_text:
        parts.append(f"可见文字：{analysis.ocr_text}")
    if analysis.transcript_text:
        parts.append(f"字幕/转写：{analysis.transcript_text}")
    if brand:
        parts.append(f"识别到品牌：{brand}。")
    if material_grade:
        parts.append(f"识别到材质：{material_grade}。")

    if not analysis.visual_summary and not analysis.transcript_text:
        parts.append("请人工 review 描述、标签和推荐话术后再入库。")
    return "".join(parts)


def _recommended_script(
    material_type: str,
    brand: str | None,
    scenario: str,
    analysis: MediaAnalysis,
) -> str:
    media_label = "视频" if material_type == "video" else "图片"
    brand_text = f"{brand} " if brand else ""
    if analysis.visual_summary:
        return f"这是{brand_text}{scenario}{media_label}，可以让客户看到{analysis.visual_summary}。"
    return f"这是{brand_text}{scenario}{media_label}，可以发给客户确认细节。"


def _review_to_material_payload(item: MaterialReviewItem) -> dict[str, Any]:
    return {
        "name": item.name,
        "file_path": item.file_path,
        "material_type": item.material_type,
        "product_type": item.product_type,
        "scenario": item.scenario,
        "brand": item.brand,
        "material_grade": item.material_grade,
        "description": item.description,
        "recommended_script": item.recommended_script,
        "tags": item.tags,
    }


def _serialize_review(item: MaterialReviewItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_path": item.source_path,
        "name": item.name,
        "file_path": item.file_path,
        "material_type": item.material_type,
        "product_type": item.product_type,
        "scenario": item.scenario,
        "brand": item.brand,
        "material_grade": item.material_grade,
        "description": item.description,
        "recommended_script": item.recommended_script,
        "tags": item.tags,
        "status": item.status,
        "material_id": item.material_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }
