from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.material_review import (
    InvalidMaterialReviewTransitionError,
    analyze_material_path,
    confirm_material_review,
    list_material_reviews,
    reject_material_review,
    scan_material_reviews,
    update_material_review,
)

router = APIRouter(prefix="/api/material-reviews", tags=["material-reviews"])


class MaterialReviewScanRequest(BaseModel):
    directory_path: str = Field(..., min_length=1)
    product_type: str = "brake_pad"
    recursive: bool = True


class MaterialAnalyzeRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    product_type: str = "brake_pad"
    distribution_id: str | None = None


class MaterialReviewUpdateRequest(BaseModel):
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


@router.post("/analyze")
def analyze_material_endpoint(request: MaterialAnalyzeRequest) -> dict[str, Any]:
    try:
        return analyze_material_path(
            request.file_path,
            product_type=request.product_type,
            distribution_id=request.distribution_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scan")
def scan_material_reviews_endpoint(
    request: MaterialReviewScanRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return scan_material_reviews(
            db,
            request.directory_path,
            product_type=request.product_type,
            recursive=request.recursive,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_material_reviews_endpoint(
    status: str = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_material_reviews(db, status=status, page=page, page_size=page_size)


@router.patch("/{review_id}")
def update_material_review_endpoint(
    review_id: int,
    request: MaterialReviewUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        item = update_material_review(db, review_id, request.model_dump(exclude_unset=True))
    except InvalidMaterialReviewTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Material review not found")
    return item


@router.post("/{review_id}/confirm")
def confirm_material_review_endpoint(
    review_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        item = confirm_material_review(db, review_id)
    except InvalidMaterialReviewTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Material review not found")
    return item


@router.post("/{review_id}/reject")
def reject_material_review_endpoint(
    review_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        item = reject_material_review(db, review_id)
    except InvalidMaterialReviewTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Material review not found")
    return item
