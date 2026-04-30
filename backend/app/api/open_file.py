"""Open file with system default application."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["misc"])


class OpenFileRequest(BaseModel):
    path: str


@router.post("/api/open-file")
async def open_file(req: OpenFileRequest):
    """Open a file with the system's default application."""
    file_path = Path(req.path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"不是有效文件: {req.path}")

    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["open", str(file_path)], check=True)
        elif system == "Windows":
            os.startfile(str(file_path))  # type: ignore[attr-defined]
        elif system == "Linux":
            subprocess.run(["xdg-open", str(file_path)], check=True)
        else:
            raise HTTPException(status_code=500, detail=f"不支持的操作系统: {system}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开文件失败: {e}")

    return {"ok": True, "path": req.path}
