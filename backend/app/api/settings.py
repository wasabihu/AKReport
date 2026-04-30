"""Settings read/update endpoint."""
import platform
from pathlib import Path
import subprocess

from fastapi import APIRouter, HTTPException

from app.dependencies import get_rate_limiter, get_settings
from app.models import ErrorResponse, RateLimitSnapshot, SuccessResponse

router = APIRouter(tags=["settings"])


def _settings_payload() -> dict:
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    return {
        "request_interval_seconds": rate_limiter.base_interval,
        "concurrency": settings.default_concurrency,
        "auto_slowdown": settings.auto_slowdown,
        "default_save_dir": str(settings.default_save_dir),
        "default_request_interval_seconds": rate_limiter.base_interval,
        "min_request_interval_seconds": settings.min_request_interval_seconds,
        "max_concurrency": settings.max_concurrency,
        "max_retries": settings.max_retries,
        "score_threshold": settings.score_threshold,
        "rate_limit_snapshots": [s.model_dump() for s in rate_limiter.snapshot()],
    }


def _default_picker_location(save_dir: Path) -> Path:
    if save_dir.exists():
        return save_dir
    if save_dir.parent.exists():
        return save_dir.parent
    return Path.home()


def _run_macos_folder_picker(default_location: Path) -> tuple[bool, str]:
    script = (
        'POSIX path of (choose folder '
        f'with prompt "请选择财报保存目录" default location POSIX file "{default_location}")'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return False, result.stdout.strip().rstrip("/")

    message = result.stderr.strip()
    if "User canceled" in message or result.returncode == 1:
        return True, ""

    raise RuntimeError(message or "打开访达目录选择器失败")


def _run_windows_folder_picker(default_location: Path) -> tuple[bool, str]:
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '请选择财报保存目录'
$dialog.SelectedPath = '{str(default_location).replace("'", "''")}'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
  [Console]::Out.Write($dialog.SelectedPath)
}} else {{
  exit 1
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return False, result.stdout.strip()
    if result.returncode == 1:
        return True, ""

    raise RuntimeError(result.stderr.strip() or "打开 Windows 目录选择器失败")


def _run_tk_folder_picker(default_location: Path) -> tuple[bool, str]:
    script = """
import sys
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askdirectory(
    title="请选择财报保存目录",
    initialdir=sys.argv[1],
    mustexist=False,
)
root.destroy()
if path:
    print(path, end="")
else:
    sys.exit(1)
"""
    result = subprocess.run(
        ["python3", "-c", script, str(default_location)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return False, result.stdout.strip()
    if result.returncode == 1:
        return True, ""

    raise RuntimeError(result.stderr.strip() or "打开目录选择器失败")


def _choose_save_dir(default_location: Path) -> tuple[bool, str]:
    system = platform.system()
    if system == "Darwin":
        return _run_macos_folder_picker(default_location)
    if system == "Windows":
        return _run_windows_folder_picker(default_location)
    return _run_tk_folder_picker(default_location)


@router.get("/api/settings", response_model=SuccessResponse)
async def get_settings_api():
    """Get current application settings."""
    return SuccessResponse(
        data=_settings_payload(),
        message="ok",
    )


@router.post(
    "/api/settings/browse-save-dir",
    response_model=SuccessResponse,
    responses={500: {"model": ErrorResponse}},
)
async def browse_save_dir():
    """Open a native folder picker and update the default save directory."""
    settings = get_settings()
    current_dir = str(settings.default_save_dir)
    default_location = _default_picker_location(settings.default_save_dir)

    try:
        cancelled, selected_dir = _choose_save_dir(default_location)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_PICKER_UNAVAILABLE",
                "message": "当前系统不支持打开目录选择器",
            },
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_PICKER_TIMEOUT",
                "message": "目录选择超时",
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_PICKER_ERROR",
                "message": str(exc),
            },
        ) from exc

    if cancelled:
        return SuccessResponse(
            data={"cancelled": True, "default_save_dir": current_dir},
            message="已取消选择",
        )

    if not selected_dir:
        return SuccessResponse(
            data={"cancelled": True, "default_save_dir": current_dir},
            message="未选择目录",
        )

    settings.default_save_dir = Path(selected_dir).expanduser()
    return SuccessResponse(
        data={**_settings_payload(), "cancelled": False},
        message="保存目录已更新",
    )


@router.put(
    "/api/settings",
    response_model=SuccessResponse,
    responses={400: {"model": ErrorResponse}},
)
async def update_settings(body: dict):
    """Update application settings (interval, concurrency limits)."""
    settings = get_settings()
    rate_limiter = get_rate_limiter()

    if "request_interval_seconds" in body or "default_request_interval_seconds" in body:
        new_interval = body.get("request_interval_seconds", body.get("default_request_interval_seconds"))
        if not rate_limiter.validate_interval(new_interval):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INTERVAL", "message": f"间隔不能低于{settings.min_request_interval_seconds}秒"},
            )
        settings.default_request_interval_seconds = new_interval
        rate_limiter.base_interval = new_interval

    if "concurrency" in body:
        new_concurrency = int(body["concurrency"])
        if not rate_limiter.validate_concurrency(new_concurrency, settings.max_concurrency):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CONCURRENCY", "message": f"并发数必须在 1-{settings.max_concurrency} 之间"},
            )
        settings.default_concurrency = new_concurrency

    if "auto_slowdown" in body:
        settings.auto_slowdown = bool(body["auto_slowdown"])

    if "default_save_dir" in body:
        settings.default_save_dir = Path(body["default_save_dir"]).expanduser()

    if "score_threshold" in body:
        settings.score_threshold = int(body["score_threshold"])

    return SuccessResponse(
        data=_settings_payload(),
        message="设置已更新",
    )
