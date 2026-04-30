from pathlib import Path

from app.config import Settings


def test_windows_default_save_dir_is_c_reports(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")

    settings = Settings(_env_file=None)

    assert settings.default_save_dir == Path("C:/reports")


def test_non_windows_default_save_dir_uses_user_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    settings = Settings(_env_file=None)

    assert settings.default_save_dir == tmp_path / "Downloads" / "reports"
