from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"active_page": "qa", "page_title": "AI 问答"},
    )


@router.get("/knowledge")
def knowledge(request: Request):
    return templates.TemplateResponse(
        request,
        "knowledge.html",
        {"active_page": "knowledge", "page_title": "知识库管理"},
    )


@router.get("/materials")
def materials_page(request: Request):
    return templates.TemplateResponse(
        request,
        "materials.html",
        {"active_page": "materials", "page_title": "素材管理"},
    )


@router.get("/speech-templates")
def speech_templates_page(request: Request):
    return templates.TemplateResponse(
        request,
        "speech_templates.html",
        {"active_page": "speech", "page_title": "话术模板"},
    )
