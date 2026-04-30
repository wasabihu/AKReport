"""Excel/CSV upload endpoint for batch stock code import."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.models import ErrorResponse, SuccessResponse
from app.services.excel_importer import ExcelImporter

router = APIRouter(prefix="/api/import", tags=["import"])


@router.get("/template")
async def download_template():
    """Download the stock import template workbook."""
    template_path = Path(__file__).resolve().parents[3] / "股票导入模板.xlsx"
    if not template_path.exists():
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error={"code": "TEMPLATE_NOT_FOUND", "message": "导入模板文件不存在"}
            ).model_dump(),
        )

    return FileResponse(
        path=template_path,
        filename="股票导入模板.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/excel", response_model=SuccessResponse)
async def import_excel(file: UploadFile = File(...)) -> dict:
    """Upload an Excel or CSV file and extract stock codes."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={"code": "INVALID_FORMAT", "message": "仅支持 .xlsx/.xls/.csv 文件"}
            ).model_dump(),
        )

    tmp_path = Path(tempfile.gettempdir()) / f"akshare_import_{file.filename}"
    try:
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        importer = ExcelImporter()
        results = importer.import_file(tmp_path)

        return SuccessResponse(
            data={
                "codes": results,
                "count": len(results),
            },
            message=f"成功导入 {len(results)} 条股票代码",
        ).model_dump()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={"code": "PARSE_ERROR", "message": str(e)}
            ).model_dump(),
        )
    finally:
        tmp_path.unlink(missing_ok=True)
