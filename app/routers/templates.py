from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.speech_template import (
    InvalidTemplateTransitionError,
    confirm_template,
    disable_template,
    list_templates,
    summarize_chat_to_template,
    update_template,
)


router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateSummarizeRequest(BaseModel):
    source_chat: str = Field(..., min_length=1)


class TemplateUpdateRequest(BaseModel):
    scenario: str | None = None
    customer_question: str | None = None
    style_notes: str | None = None
    standard_reply: str | None = None
    forbidden_words: str | None = None
    recommended_material_ids: str | None = None


@router.post("/summarize")
def summarize_template(
    request: TemplateSummarizeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    source_chat = request.source_chat.strip()
    if not source_chat:
        raise HTTPException(status_code=400, detail="source_chat 不能为空")
    return summarize_chat_to_template(db, source_chat)


@router.get("")
def list_templates_endpoint(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_templates(db)


@router.patch("/{template_id}")
def update_template_endpoint(
    template_id: int,
    request: TemplateUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    template = update_template(db, template_id, request.model_dump(exclude_unset=True))
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/{template_id}/confirm")
def confirm_template_endpoint(
    template_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        template = confirm_template(db, template_id)
    except InvalidTemplateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/{template_id}/disable")
def disable_template_endpoint(
    template_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        template = disable_template(db, template_id)
    except InvalidTemplateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
