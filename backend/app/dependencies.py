"""FastAPI dependency injection."""
from __future__ import annotations

from app.config import Settings
from app.services.cninfo_client import CNInfoClient
from app.services.downloader import Downloader
from app.services.rate_limiter import RateLimiter
from app.storage.database import Database
from app.storage.repositories import TaskRepository

# Global singletons (initialized in main.py lifespan)
_settings: Settings | None = None
_database: Database | None = None
_rate_limiter: RateLimiter | None = None
_cninfo_client: CNInfoClient | None = None
_downloader: Downloader | None = None
_repo: TaskRepository | None = None


def init_dependencies(settings: Settings) -> None:
    global _settings, _database, _rate_limiter, _cninfo_client, _downloader, _repo
    _settings = settings
    _database = Database(settings)
    _rate_limiter = RateLimiter(settings)
    _cninfo_client = CNInfoClient(settings, _rate_limiter)
    _downloader = Downloader(settings, _rate_limiter)
    _repo = TaskRepository(_database.connection)


def get_settings() -> Settings:
    assert _settings is not None, "Dependencies not initialized"
    return _settings


def get_database() -> Database:
    assert _database is not None, "Dependencies not initialized"
    return _database


def get_rate_limiter() -> RateLimiter:
    assert _rate_limiter is not None, "Dependencies not initialized"
    return _rate_limiter


def get_cninfo_client() -> CNInfoClient:
    assert _cninfo_client is not None, "Dependencies not initialized"
    return _cninfo_client


def get_downloader() -> Downloader:
    assert _downloader is not None, "Dependencies not initialized"
    return _downloader


def get_repo() -> TaskRepository:
    assert _repo is not None, "Dependencies not initialized"
    return _repo
