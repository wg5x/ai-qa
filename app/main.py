from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import imports, material_reviews, materials, pages, qa, templates


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(pages.router)
app.include_router(imports.router)
app.include_router(materials.router)
app.include_router(material_reviews.router)
app.include_router(templates.router)
app.include_router(qa.router)
app.include_router(qa.orders_router)
app.include_router(qa.qa_router)
app.include_router(qa.runtime_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
