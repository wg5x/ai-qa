from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ai_provider import SalesAnswer, generate_sales_answer
from app.services.distribution_runtime import (
    fetch_runtime_distribution_config,
    provider_from_distribution,
)
from app.services.order_compare import compare_order_items
from app.services.prompt_builder import build_sales_prompt_context, render_sales_prompt
from app.services.quote_search import search_historical_prices


router = APIRouter(prefix="/api/search", tags=["search"])
orders_router = APIRouter(prefix="/api/orders", tags=["orders"])
qa_router = APIRouter(prefix="/api/qa", tags=["qa"])
runtime_router = APIRouter(prefix="/api/runtime", tags=["runtime"])


class OrderCompareRequest(BaseModel):
    customer_name: str = Field(..., min_length=1)
    items: list[dict[str, Any]] = Field(default_factory=list)
    part_numbers: list[str] = Field(default_factory=list)


class QAAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    distribution_id: str | None = None


@router.get("/prices")
def search_prices(
    customer: str = Query(..., min_length=1),
    part_number: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return search_historical_prices(
        db,
        customer_name=customer,
        part_number=part_number,
    )


@orders_router.post("/compare")
def compare_orders(
    request: OrderCompareRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    items = request.items or [
        {"part_number": part_number} for part_number in request.part_numbers
    ]
    return compare_order_items(db, customer_name=request.customer_name, items=items)


@qa_router.post("/ask")
def ask_question(
    request: QAAskRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    context = build_sales_prompt_context(
        db,
        question,
        conversation_history=request.conversation_history,
    )
    provider_context = {
        **context,
        "rendered_prompt": render_sales_prompt(context),
    }
    try:
        provider = (
            provider_from_distribution(request.distribution_id.strip())
            if request.distribution_id and request.distribution_id.strip()
            else None
        )
        answer = generate_sales_answer(question, provider_context, provider=provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize_sales_answer(answer)


def _serialize_sales_answer(answer: SalesAnswer) -> dict[str, object]:
    return {
        "reply_thinking": answer.reply_thinking,
        "standard_reply": answer.standard_reply,
        "references": answer.references,
        "recommended_materials": answer.recommended_materials,
        "warnings": answer.warnings,
    }


@runtime_router.get("/distributions/{distribution_id}")
def runtime_distribution(distribution_id: str) -> dict[str, object]:
    try:
        config = fetch_runtime_distribution_config(distribution_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _public_runtime_config(config)


def _public_runtime_config(config: dict[str, object]) -> dict[str, object]:
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    app = config.get("app") if isinstance(config.get("app"), dict) else {}
    return {
        "distributionId": config.get("distributionId"),
        "status": config.get("status"),
        "app": {
            "name": app.get("name"),
            "url": app.get("url"),
        },
        "model": {
            "provider": model.get("provider"),
            "model": model.get("model"),
            "apiBaseUrl": model.get("apiBaseUrl"),
            "enabled": model.get("enabled"),
            "parameters": model.get("parameters") if isinstance(model.get("parameters"), dict) else {},
        },
    }
