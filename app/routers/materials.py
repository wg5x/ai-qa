from typing import Any
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Material
from app.services.material_search import (
    create_material,
    delete_material,
    list_materials,
    paginate_materials,
    search_materials,
    update_material,
)


router = APIRouter(prefix="/api/materials", tags=["materials"])

ALLOWED_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi"}


class MaterialPayload(BaseModel):
    name: str | None = None
    file_path: str | None = None
    material_type: str | None = None
    product_type: str | None = None
    scenario: str | None = None
    brand: str | None = None
    material_grade: str | None = None
    description: str | None = None
    recommended_script: str | None = None
    tags: str | None = None


@router.post("/upload")
async def upload_material_file(file: UploadFile = File(...)) -> dict[str, str]:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的素材文件类型")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_upload_path(settings.upload_dir / filename)
    content = await file.read()
    target.write_bytes(content)
    return {"file_path": str(target), "filename": filename}


@router.post("")
def create_material_endpoint(
    payload: MaterialPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_material(db, payload.model_dump(exclude_unset=True))


@router.get("")
def list_materials_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return paginate_materials(list_materials(db), page=page, page_size=page_size)


@router.get("/search")
def search_materials_endpoint(
    q: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    material_grade: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return paginate_materials(
        search_materials(
            db,
            query=q,
            scenario=scenario,
            tags=tags,
            brand=brand,
            material_grade=material_grade,
        ),
        page=page,
        page_size=page_size,
    )


@router.get("/{material_id}/file")
def get_material_file(
    material_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    material = db.get(Material, material_id)
    if material is None or material.material_type == "knowledge" or not material.file_path:
        raise HTTPException(status_code=404, detail="Material file not found")

    path = Path(material.file_path)
    if path.suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES or not path.is_file():
        raise HTTPException(status_code=404, detail="Material file not found")
    return FileResponse(path)


@router.patch("/{material_id}")
def update_material_endpoint(
    material_id: int,
    payload: MaterialPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    material = update_material(db, material_id, payload.model_dump(exclude_unset=True))
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@router.delete("/{material_id}")
def delete_material_endpoint(
    material_id: int,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    deleted = delete_material(db, material_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Material not found")
    return {"deleted": True}


def _unique_upload_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 10000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=500, detail="无法生成上传文件名")
