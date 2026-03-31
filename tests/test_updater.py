"""Tests for the self-update module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_migrate import __version__
from agent_migrate.updater import (
    VersionInfo,
    _is_newer,
    check_version,
    get_current_version,
    run_update,
)


# ── get_current_version ─────────────────────────────────────────────────────


def test_get_current_version_matches_package():
    assert get_current_version() == __version__


# ── _is_newer ────────────────────────────────────────────────────────────────


def test_is_newer_major():
    assert _is_newer("1.0.0", "0.1.0") is True


def test_is_newer_minor():
    assert _is_newer("0.2.0", "0.1.0") is True


def test_is_newer_patch():
    assert _is_newer("0.1.1", "0.1.0") is True


def test_is_not_newer_same():
    assert _is_newer("0.1.0", "0.1.0") is False


def test_is_not_newer_older():
    assert _is_newer("0.1.0", "0.2.0") is False


def test_is_newer_handles_invalid_gracefully():
    # Non-numeric parts fallback to string comparison
    assert _is_newer("abc", "abc") is False
    assert _is_newer("abc", "def") is True  # string != comparison


# ── check_version ────────────────────────────────────────────────────────────


@patch("agent_migrate.updater.fetch_latest_version")
def test_check_version_update_available(mock_fetch: MagicMock):
    mock_fetch.return_value = "99.0.0"
    info = check_version()
    assert info.current == __version__
    assert info.latest == "99.0.0"
    assert info.update_available is True
    assert info.error is None


@patch("agent_migrate.updater.fetch_latest_version")
def test_check_version_up_to_date(mock_fetch: MagicMock):
    mock_fetch.return_value = __version__
    info = check_version()
    assert info.update_available is False
    assert info.error is None


@patch("agent_migrate.updater.fetch_latest_version")
def test_check_version_network_error(mock_fetch: MagicMock):
    mock_fetch.return_value = None
    info = check_version()
    assert info.update_available is False
    assert info.error is not None


@patch("agent_migrate.updater.fetch_latest_version")
def test_check_version_exception(mock_fetch: MagicMock):
    mock_fetch.side_effect = RuntimeError("network down")
    info = check_version()
    assert info.update_available is False
    assert info.error is not None


# ── run_update ───────────────────────────────────────────────────────────────


@patch("agent_migrate.updater._detect_installer", return_value="pip")
@patch("subprocess.run")
def test_run_update_success_pip(mock_run: MagicMock, mock_detect: MagicMock):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    success, msg = run_update()
    assert success is True
    assert "successful" in msg.lower()
    # Should use sys.executable -m pip
    call_args = mock_run.call_args[0][0]
    assert "-m" in call_args
    assert "pip" in call_args


@patch("agent_migrate.updater._detect_installer", return_value="uv")
@patch("subprocess.run")
def test_run_update_success_uv(mock_run: MagicMock, mock_detect: MagicMock):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    success, msg = run_update()
    assert success is True
    call_args = mock_run.call_args[0][0]
    assert "uv" in call_args


@patch("agent_migrate.updater._detect_installer", return_value="pip")
@patch("subprocess.run")
def test_run_update_failure(mock_run: MagicMock, mock_detect: MagicMock):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ERROR: no matching dist")
    success, msg = run_update()
    assert success is False
    assert "failed" in msg.lower()


@patch("agent_migrate.updater._detect_installer", return_value="uv")
@patch("subprocess.run")
def test_run_update_uv_fallback_to_system(mock_run: MagicMock, mock_detect: MagicMock):
    # First call fails, second (with --system) succeeds
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="error"),
        MagicMock(returncode=0, stdout="ok", stderr=""),
    ]
    success, msg = run_update()
    assert success is True
    assert mock_run.call_count == 2
    # Second call should include --system
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "--system" in second_call_args


@patch("agent_migrate.updater._detect_installer", return_value="pip")
@patch("subprocess.run")
def test_run_update_timeout(mock_run: MagicMock, mock_detect: MagicMock):
    import subprocess as sp

    mock_run.side_effect = sp.TimeoutExpired(cmd="pip", timeout=120)
    success, msg = run_update()
    assert success is False
    assert "timed out" in msg.lower()


# ── VersionInfo ──────────────────────────────────────────────────────────────


def test_version_info_dataclass():
    info = VersionInfo(current="0.1.0", latest="0.2.0", update_available=True)
    assert info.current == "0.1.0"
    assert info.latest == "0.2.0"
    assert info.update_available is True
    assert info.error is None


def test_version_info_with_error():
    info = VersionInfo(current="0.1.0", latest=None, update_available=False, error="fail")
    assert info.error == "fail"
