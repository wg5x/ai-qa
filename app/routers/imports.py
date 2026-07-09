import json
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import PROJECT_ROOT, settings
from app.database import get_db
from app.models import ContractRecord, Material, QuoteRecord
from app.services.excel_importer import (
    InvalidExcelFileError,
    import_contract_excel,
    import_quote_excel,
)
from app.services.material_search import paginate_materials
from app.services.raw_material_seed import (
    import_manual_knowledge,
    import_media_directory,
    list_manual_knowledge,
)


router = APIRouter(prefix="/api/imports", tags=["imports"])
DEFAULT_MANUAL = PROJECT_ROOT / "raw" / "260706业务员谈单手册_v4.0.docx"
DEFAULT_MEDIA_DIR = PROJECT_ROOT / "raw" / "2026.7.7刹车片" / "小片"
DEFAULT_QUOTES = PROJECT_ROOT / "data" / "samples" / "sample_quotes.xlsx"
DEFAULT_CONTRACTS = PROJECT_ROOT / "data" / "samples" / "sample_contracts.xlsx"
KNOWLEDGE_EDIT_PREFIX = "__knowledge_edit__:"


class KnowledgeItemPayload(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: str | None = None


@router.post("/quotes")
async def import_quotes(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    content = await file.read()
    try:
        return import_quote_excel(db, BytesIO(content), source_file=file.filename)
    except InvalidExcelFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/contracts")
async def import_contracts(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    content = await file.read()
    try:
        return import_contract_excel(db, BytesIO(content), source_file=file.filename)
    except InvalidExcelFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/manual")
def import_manual(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    manual_path = DEFAULT_MANUAL
    if not manual_path.exists():
        raise HTTPException(status_code=404, detail=f"谈单手册不存在: {manual_path}")
    return import_manual_knowledge(db, manual_path)


@router.get("/manual/fragments")
def list_manual_fragments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return paginate_materials(
        list_manual_knowledge(db),
        page=page,
        page_size=page_size,
    )


@router.post("/knowledge")
def import_knowledge(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    missing_files = [
        str(path)
        for path in (DEFAULT_QUOTES, DEFAULT_CONTRACTS, DEFAULT_MANUAL)
        if not path.exists()
    ]
    if missing_files:
        raise HTTPException(status_code=404, detail=f"知识库文件不存在: {', '.join(missing_files)}")

    with DEFAULT_QUOTES.open("rb") as quote_file:
        quotes_result = import_quote_excel(db, quote_file, source_file=str(DEFAULT_QUOTES))
    with DEFAULT_CONTRACTS.open("rb") as contract_file:
        contracts_result = import_contract_excel(
            db,
            contract_file,
            source_file=str(DEFAULT_CONTRACTS),
        )
    manual_result = import_manual_knowledge(db, DEFAULT_MANUAL)

    return {
        "quotes": quotes_result,
        "contracts": contracts_result,
        "manual": manual_result,
    }


@router.get("/knowledge/items")
def list_knowledge_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return paginate_materials(
        _knowledge_items(db),
        page=page,
        page_size=page_size,
    )


@router.post("/knowledge/upload")
async def upload_knowledge_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename:
        raise HTTPException(status_code=400, detail="请选择知识库文件")
    content = await file.read()
    source_type = _detect_knowledge_source_type(filename, content)

    upload_dir = settings.upload_dir / "knowledge"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_upload_path(upload_dir / filename)
    target.write_bytes(content)

    try:
        if source_type == "quote":
            result = import_quote_excel(db, BytesIO(content), source_file=str(target))
        elif source_type == "contract":
            result = import_contract_excel(db, BytesIO(content), source_file=str(target))
        else:
            result = import_manual_knowledge(db, target, source_label=target.stem)
    except InvalidExcelFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "source_type": source_type,
        "source_file": str(target),
        "result": result,
    }


@router.patch("/knowledge/{source_type}/{record_id}")
def update_knowledge_item(
    source_type: str,
    record_id: int,
    payload: KnowledgeItemPayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    data = payload.model_dump(exclude_unset=True)
    if source_type == "manual":
        material = db.get(Material, record_id)
        if material is None or material.material_type != "knowledge":
            raise HTTPException(status_code=404, detail="知识片段不存在")
        if "title" in data:
            material.name = data["title"]
        if "description" in data:
            material.description = data["description"]
        if "tags" in data:
            material.tags = data["tags"]
        db.commit()
        db.refresh(material)
        return _serialize_manual_item(
            {
                "id": material.id,
                "name": material.name,
                "description": material.description,
                "tags": material.tags,
                "file_path": material.file_path,
                "created_at": material.created_at.isoformat() if material.created_at else None,
            }
        )

    if source_type == "quote":
        record = db.get(QuoteRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="知识记录不存在")
        current = _serialize_quote_item(record)
        _update_record_knowledge_note(record, current, data)
        db.commit()
        db.refresh(record)
        return _serialize_quote_item(record)

    if source_type == "contract":
        record = db.get(ContractRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="知识记录不存在")
        current = _serialize_contract_item(record)
        _update_record_knowledge_note(record, current, data)
        db.commit()
        db.refresh(record)
        return _serialize_contract_item(record)

    raise HTTPException(status_code=404, detail="知识记录不存在")


@router.post("/materials")
def import_materials(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not DEFAULT_MEDIA_DIR.exists():
        raise HTTPException(status_code=404, detail=f"素材目录不存在: {DEFAULT_MEDIA_DIR}")
    return import_media_directory(db, DEFAULT_MEDIA_DIR)


def _knowledge_items(db: Session) -> list[dict[str, object]]:
    quote_items = [
        _serialize_quote_item(record)
        for record in db.scalars(select(QuoteRecord).order_by(QuoteRecord.id.desc()))
    ]
    contract_items = [
        _serialize_contract_item(record)
        for record in db.scalars(select(ContractRecord).order_by(ContractRecord.id.desc()))
    ]
    manual_items = [_serialize_manual_item(item) for item in list_manual_knowledge(db)]
    source_priority = {"quote": 0, "contract": 1, "manual": 2}
    return sorted(
        [*quote_items, *contract_items, *manual_items],
        key=lambda item: (
            source_priority.get(str(item.get("source_type")), 99),
            str(item.get("created_at") or ""),
        ),
        reverse=False,
    )


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


def _detect_knowledge_source_type(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return "manual"
    if suffix != ".xlsx":
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .docx 文件")

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="无法读取 Excel 文件，请上传有效的 .xlsx 文件") from exc

    sheet = workbook.active
    headers = {
        str(cell.value).strip()
        for cell in sheet[1]
        if cell.value is not None and str(cell.value).strip()
    }
    if "合同编号" in headers:
        return "contract"
    if "报价日期" in headers:
        return "quote"
    raise HTTPException(status_code=400, detail="无法识别 Excel 类型，请上传报价单或合同模板")


def _serialize_quote_item(record: QuoteRecord) -> dict[str, object]:
    note = _knowledge_note(record.remark)
    default_description = (
        f"{record.country or '-'} / {record.material_grade or '-'} / "
        f"{record.quantity or '-'} {record.currency or ''} {record.unit_price or ''}"
    )
    return {
        "id": f"quote-{record.id}",
        "raw_id": record.id,
        "source_type": "quote",
        "title": note.get("title") or f"报价单 · {record.customer_name or '-'} · {record.part_number or '-'}",
        "description": note.get("description") or default_description,
        "tags": note.get("tags") or "",
        "source_file": record.source_file,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _serialize_contract_item(record: ContractRecord) -> dict[str, object]:
    note = _knowledge_note(record.remark)
    default_description = (
        f"{record.country or '-'} / {record.part_number or '-'} / "
        f"{record.material_grade or '-'} / {record.quantity or '-'}"
    )
    return {
        "id": f"contract-{record.id}",
        "raw_id": record.id,
        "source_type": "contract",
        "title": note.get("title") or f"合同 · {record.contract_no or '-'} · {record.customer_name or '-'}",
        "description": note.get("description") or default_description,
        "tags": note.get("tags") or "",
        "source_file": record.source_file,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _serialize_manual_item(item: dict[str, object]) -> dict[str, object]:
    return {
        "id": f"manual-{item['id']}",
        "raw_id": item["id"],
        "source_type": "manual",
        "title": item["name"],
        "description": item["description"],
        "tags": item["tags"],
        "source_file": item["file_path"],
        "created_at": item["created_at"],
    }


def _update_record_knowledge_note(
    record: QuoteRecord | ContractRecord,
    current: dict[str, object],
    data: dict[str, object],
) -> None:
    note = _knowledge_note(record.remark)
    original_remark = note.get("original_remark")
    if original_remark is None and record.remark and not record.remark.startswith(KNOWLEDGE_EDIT_PREFIX):
        original_remark = record.remark
    updated = {
        "title": data.get("title", current.get("title")),
        "description": data.get("description", current.get("description")),
        "tags": data.get("tags", current.get("tags")),
        "original_remark": original_remark,
    }
    record.remark = f"{KNOWLEDGE_EDIT_PREFIX}{json.dumps(updated, ensure_ascii=False)}"


def _knowledge_note(remark: str | None) -> dict[str, object]:
    if not remark or not remark.startswith(KNOWLEDGE_EDIT_PREFIX):
        return {}
    try:
        payload = json.loads(remark.removeprefix(KNOWLEDGE_EDIT_PREFIX))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
