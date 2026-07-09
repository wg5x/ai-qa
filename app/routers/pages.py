from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.config import settings

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def page_context(request: Request, active_page: str, page_title: str) -> dict[str, str | Request]:
    return {
        "request": request,
        "active_page": active_page,
        "page_title": page_title,
        "base_path": settings.base_path,
    }


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        page_context(request, "qa", "AI 问答"),
    )


@router.get("/knowledge")
def knowledge(request: Request):
    return templates.TemplateResponse(
        request,
        "knowledge.html",
        page_context(request, "knowledge", "知识库管理"),
    )


@router.get("/materials")
def materials_page(request: Request):
    return templates.TemplateResponse(
        request,
        "materials.html",
        page_context(request, "materials", "素材库"),
    )


@router.get("/speech-templates")
def speech_templates_page(request: Request):
    return templates.TemplateResponse(
        request,
        "speech_templates.html",
        page_context(request, "speech", "话术库"),
    )
