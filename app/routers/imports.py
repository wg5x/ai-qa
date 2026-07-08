from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.excel_importer import (
    InvalidExcelFileError,
    import_contract_excel,
    import_quote_excel,
)


router = APIRouter(prefix="/api/imports", tags=["imports"])


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
