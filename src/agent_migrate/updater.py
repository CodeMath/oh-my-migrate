"""Self-update logic for agent-migrate.

Checks the latest version from GitHub and upgrades via pip/uv.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from agent_migrate import __version__

REPO = "CodeMath/oh-my-migrate"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
GITHUB_PYPROJECT_URL = (
    f"https://raw.githubusercontent.com/{REPO}/main/pyproject.toml"
)
GIT_INSTALL_URL = f"git+https://github.com/{REPO}.git"


@dataclass(frozen=True)
class VersionInfo:
    current: str
    latest: str | None
    update_available: bool
    error: str | None = None


def get_current_version() -> str:
    return __version__


def fetch_latest_version() -> str | None:
    """Fetch the latest version from GitHub.

    Tries the releases API first, falls back to reading pyproject.toml from main.
    """
    # Try GitHub Releases API
    version = _fetch_from_releases()
    if version:
        return version

    # Fallback: read pyproject.toml from main branch
    return _fetch_from_pyproject()


def _fetch_from_releases() -> str | None:
    """Fetch latest version from GitHub Releases API."""
    try:
        import json as _json  # noqa: PLC0415

        req = Request(GITHUB_API_URL, headers={"Accept": "application/vnd.github.v3+json"})
        with urlopen(req, timeout=5) as resp:  # noqa: S310
            data = _json.loads(resp.read().decode())
        tag = data.get("tag_name", "")
        return tag.lstrip("v") if tag else None
    except (URLError, OSError, KeyError, ValueError):
        return None


def _fetch_from_pyproject() -> str | None:
    """Fetch version from pyproject.toml on main branch."""
    try:
        req = Request(GITHUB_PYPROJECT_URL)
        with urlopen(req, timeout=5) as resp:  # noqa: S310
            content = resp.read().decode()
        for line in content.splitlines():
            if line.strip().startswith("version"):
                # version = "0.2.0"
                _, _, val = line.partition("=")
                return val.strip().strip('"').strip("'")
    except (URLError, OSError, ValueError):
        pass
    return None


def check_version() -> VersionInfo:
    """Check current vs latest version."""
    current = get_current_version()
    try:
        latest = fetch_latest_version()
    except Exception:  # noqa: BLE001
        return VersionInfo(
            current=current,
            latest=None,
            update_available=False,
            error="Failed to check latest version from GitHub",
        )

    if latest is None:
        return VersionInfo(
            current=current,
            latest=None,
            update_available=False,
            error="Could not determine latest version",
        )

    update_available = _is_newer(latest, current)
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=update_available,
    )


def run_update() -> tuple[bool, str]:
    """Run self-update. Returns (success, message)."""
    # Determine package manager
    installer = _detect_installer()

    try:
        if installer == "uv":
            result = subprocess.run(
                ["uv", "pip", "install", "--upgrade", GIT_INSTALL_URL],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                # Try with --system flag
                result = subprocess.run(
                    ["uv", "pip", "install", "--upgrade", "--system", GIT_INSTALL_URL],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
        else:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", GIT_INSTALL_URL],
                capture_output=True,
                text=True,
                timeout=120,
            )

        if result.returncode == 0:
            return True, "Update successful. Restart agent-migrate to use the new version."
        return False, f"Update failed:\n{result.stderr.strip()}"

    except subprocess.TimeoutExpired:
        return False, "Update timed out after 120 seconds"
    except FileNotFoundError:
        return False, f"Package manager '{installer}' not found"


def _detect_installer() -> str:
    """Detect available package installer (uv preferred over pip)."""
    if shutil.which("uv"):
        return "uv"
    return "pip"


def _is_newer(latest: str, current: str) -> bool:
    """Compare version strings (semver-like). Returns True if latest > current."""
    try:
        latest_parts = [int(x) for x in latest.split(".")]
        current_parts = [int(x) for x in current.split(".")]
        return latest_parts > current_parts
    except (ValueError, AttributeError):
        return latest != current
