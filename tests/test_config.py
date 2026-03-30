"""Tests for ConfigDetector, AlembicDetector, and ModelDiscovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_migrate.config import AlembicDetector, ConfigDetector, ModelDiscovery
from agent_migrate.exceptions import ConfigNotFoundError

# All DB-URL env vars that ConfigDetector checks
_ALL_DB_VARS = ("DATABASE_URL", "DB_URL", "POSTGRES_URL", "SQLALCHEMY_DATABASE_URI")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all DB-URL env vars so tests start from a clean slate."""
    for var in _ALL_DB_VARS:
        monkeypatch.delenv(var, raising=False)


# ── 1. DATABASE_URL from environment ─────────────────────────────────────────

def test_detect_database_url_from_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/envdb")
    url = ConfigDetector().detect(tmp_path)
    assert url == "postgresql://u:p@localhost/envdb"


# ── 2. DB_URL from .env file ─────────────────────────────────────────────────

def test_detect_db_url_from_env_file(clean_env: None, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DB_URL=postgresql://u:p@localhost/dotenvdb\n")
    url = ConfigDetector().detect(tmp_path)
    assert url == "postgresql://u:p@localhost/dotenvdb"


# ── 3. sqlalchemy.url from alembic.ini ───────────────────────────────────────

def test_detect_from_alembic_ini(clean_env: None, tmp_path: Path) -> None:
    (tmp_path / "alembic.ini").write_text(
        "[alembic]\nsqlalchemy.url = postgresql://u:p@localhost/alembicdb\n"
    )
    url = ConfigDetector().detect(tmp_path)
    assert url == "postgresql://u:p@localhost/alembicdb"


# ── 4. Explicit --db-url is highest priority ─────────────────────────────────

def test_explicit_url_overrides_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://env:pass@localhost/envdb")
    url = ConfigDetector().detect(
        tmp_path, explicit_url="postgresql://cli:pass@localhost/clidb"
    )
    assert url == "postgresql://cli:pass@localhost/clidb"


# ── 5. ConfigNotFoundError when nothing is configured ────────────────────────

def test_config_not_found_error(clean_env: None, tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError):
        ConfigDetector().detect(tmp_path)


# ── 6. ModelDiscovery finds fixtures/fastapi_basic/app/models.py ─────────────

def test_model_discovery_finds_models() -> None:
    fixtures_root = Path(__file__).parent.parent / "fixtures" / "fastapi_basic"
    found = ModelDiscovery().discover(fixtures_root)
    names = [p.name for p in found]
    assert "models.py" in names


# ── 7. ModelDiscovery skips venv directories ─────────────────────────────────

def test_model_discovery_skips_venv(tmp_path: Path) -> None:
    # File inside venv — must be skipped
    venv_pkg = tmp_path / "venv" / "lib" / "site-packages"
    venv_pkg.mkdir(parents=True)
    venv_model = venv_pkg / "fake_model.py"
    venv_model.write_text("from sqlalchemy.orm import DeclarativeBase\n")

    # File outside venv — must be found
    (tmp_path / "app").mkdir()
    real_model = tmp_path / "app" / "models.py"
    real_model.write_text("from sqlalchemy.orm import DeclarativeBase\n")

    found = ModelDiscovery().discover(tmp_path)
    assert real_model in found
    assert venv_model not in found


# ── 8. AlembicDetector: alembic/ + alembic.ini → AlembicConfig ───────────────

def test_alembic_detector_finds_project(tmp_path: Path) -> None:
    alembic_dir = tmp_path / "alembic"
    alembic_dir.mkdir()
    (alembic_dir / "versions").mkdir()
    (tmp_path / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\n"
    )

    config = AlembicDetector().detect(tmp_path)

    assert config is not None
    assert config.ini_path == tmp_path / "alembic.ini"
    assert config.script_location == alembic_dir.resolve()
    assert config.version_locations == (alembic_dir / "versions").resolve()


# ── 9. AlembicDetector: missing alembic/ dir → None ─────────────────────────

def test_alembic_detector_returns_none_without_alembic_dir(tmp_path: Path) -> None:
    # alembic.ini present but NO alembic/ directory
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
    assert AlembicDetector().detect(tmp_path) is None
