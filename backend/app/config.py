from pathlib import Path
import platform

from pydantic import Field
from pydantic_settings import BaseSettings


def default_save_dir() -> Path:
    if platform.system() == "Windows":
        return Path("C:/reports")
    return Path.home() / "Downloads" / "reports"


class Settings(BaseSettings):
    app_name: str = "AKShare Wasa"
    app_version: str = "0.1.0"
    database_path: Path = Path("data/app.sqlite3")
    default_save_dir: Path = Field(default_factory=default_save_dir)
    default_request_interval_seconds: float = 2.0
    default_concurrency: int = 1
    auto_slowdown: bool = True
    min_request_interval_seconds: float = 1.0
    max_concurrency: int = 3
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    max_backoff_seconds: float = 60.0
    cninfo_base_url: str = "http://www.cninfo.com.cn"
    cninfo_static_base_url: str = "http://static.cninfo.com.cn"
    stock_dict_cache_ttl_seconds: int = 86400  # 24 hours
    score_threshold: int = 60

    model_config = {"env_prefix": "WASA_", "env_file": ".env"}
