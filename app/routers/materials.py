from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.material_search import (
    create_material,
    delete_material,
    list_materials,
    paginate_materials,
    search_materials,
    update_material,
)


router = APIRouter(prefix="/api/materials", tags=["materials"])


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
