"""Zero-config DB URL detection and model file discovery."""

from __future__ import annotations

import configparser
import os
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from dotenv import dotenv_values

from agent_migrate.exceptions import ConfigNotFoundError


@dataclass(frozen=True)
class MigrateConfig:
    """Loaded from .agent-migrate.toml configuration file."""
    schema: str = "public"
    exclude_tables: tuple[str, ...] = ()
    resolve_mixins: bool = True


@dataclass(frozen=True)
class AlembicConfig:
    ini_path: Path
    script_location: Path
    version_locations: Path


class ConfigDetector:
    """Detect DB URL from multiple config sources.

    Search order (later = higher priority):
    5. pyproject.toml [tool.agent-migrate] database-url
    4. alembic.ini  sqlalchemy.url
    3. .env files   (.env, .env.local, .env.development)
    2. Environment variables (DATABASE_URL, DB_URL, …)
    1. CLI --db-url  ← highest priority, checked first
    """

    ENV_VARS: tuple[str, ...] = (
        "DATABASE_URL",
        "DB_URL",
        "POSTGRES_URL",
        "SQLALCHEMY_DATABASE_URI",
    )
    ENV_FILES: tuple[str, ...] = (".env", ".env.local", ".env.development")

    def detect(self, project_root: Path, explicit_url: str | None = None) -> str:
        """Return DB URL or raise ConfigNotFoundError.

        *explicit_url* (CLI --db-url) takes highest priority.
        """
        # 1. CLI explicit value — overrides everything
        if explicit_url:
            return explicit_url

        # 2. Process environment variables
        for var in self.ENV_VARS:
            val = os.environ.get(var)
            if val:
                return val

        # 3. .env files (read as key=value without polluting os.environ)
        for env_file in self.ENV_FILES:
            path = project_root / env_file
            if path.exists():
                values = dotenv_values(path)
                for var in self.ENV_VARS:
                    val = values.get(var)
                    if val:
                        return val

        # 4. alembic.ini → [alembic] sqlalchemy.url
        alembic_ini = project_root / "alembic.ini"
        if alembic_ini.exists():
            cfg = configparser.ConfigParser()
            cfg.read(alembic_ini)
            url = cfg.get("alembic", "sqlalchemy.url", fallback=None)
            if url:
                return url

        # 5. pyproject.toml → [tool.agent-migrate] database-url
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            toml_url = data.get("tool", {}).get("agent-migrate", {}).get("database-url")
            if isinstance(toml_url, str) and toml_url:
                return toml_url

        raise ConfigNotFoundError(
            "No database URL found. "
            "Set DATABASE_URL env var, use --db-url, or add to .env / alembic.ini."
        )


class AlembicDetector:
    """Detect whether the project uses Alembic (2-Path Strategy)."""

    def detect(self, project_root: Path) -> AlembicConfig | None:
        """Return AlembicConfig if both alembic.ini and alembic/ dir exist, else None."""
        ini_path = project_root / "alembic.ini"
        alembic_dir = project_root / "alembic"

        if not ini_path.exists() or not alembic_dir.is_dir():
            return None

        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        script_location = cfg.get("alembic", "script_location", fallback="alembic")

        # script_location is relative to the directory containing alembic.ini
        script_path = (project_root / script_location).resolve()

        return AlembicConfig(
            ini_path=ini_path,
            script_location=script_path,
            version_locations=script_path / "versions",
        )


class ModelDiscovery:
    """Scan project for Python files that likely contain SQLAlchemy/SQLModel models."""

    INDICATORS: tuple[str, ...] = (
        "from sqlalchemy",
        "from sqlmodel",
        "DeclarativeBase",
        "declarative_base",
        "mapped_column",
        "Column(",
    )

    SKIP_DIRS: frozenset[str] = frozenset(
        {
            "venv",
            ".venv",
            "__pycache__",
            ".git",
            "node_modules",
            "migrations",
            "alembic",
            ".tox",
            ".mypy_cache",
        }
    )

    def discover(self, project_root: Path) -> list[Path]:
        """Return sorted list of .py files that contain SQLAlchemy indicators."""
        found: list[Path] = []
        for py_file in self._iter_python_files(project_root):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(indicator in content for indicator in self.INDICATORS):
                found.append(py_file)
        return sorted(found)

    def _iter_python_files(self, directory: Path) -> Iterator[Path]:
        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                if entry.name not in self.SKIP_DIRS:
                    yield from self._iter_python_files(entry)
            elif entry.is_file() and entry.suffix == ".py":
                yield entry


class MigrateConfigLoader:
    """Load .agent-migrate.toml configuration file."""

    CONFIG_FILENAME = ".agent-migrate.toml"

    def load(self, project_root: Path) -> MigrateConfig:
        """Load config from .agent-migrate.toml if it exists, else return defaults."""
        config_path = project_root / self.CONFIG_FILENAME
        if not config_path.exists():
            return MigrateConfig()

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        db_section = data.get("database", {})
        models_section = data.get("models", {})

        schema = db_section.get("schema", "public")
        exclude_tables_raw = db_section.get("exclude_tables", [])
        if isinstance(exclude_tables_raw, list):
            exclude_tables = tuple(str(t) for t in exclude_tables_raw)
        else:
            exclude_tables = ()

        resolve_mixins = models_section.get("resolve_mixins", True)

        return MigrateConfig(
            schema=str(schema),
            exclude_tables=exclude_tables,
            resolve_mixins=bool(resolve_mixins),
        )


def mask_db_url(url: str) -> str:
    """Return *url* with password replaced by *** (safe for logging)."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            masked_netloc = parsed.netloc.replace(
                f":{parsed.password}@", ":***@"
            )
            return urlunparse(parsed._replace(netloc=masked_netloc))
    except Exception:  # noqa: BLE001
        pass
    return url
