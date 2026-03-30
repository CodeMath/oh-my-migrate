"""Custom exceptions for agent-migrate."""

from __future__ import annotations


class AgentMigrateError(Exception):
    """Base exception."""


class ConfigNotFoundError(AgentMigrateError):
    """DB URL을 찾을 수 없음."""


class ParseError(AgentMigrateError):
    """모델 파싱 실패."""


class ConfigError(AgentMigrateError):
    """RLS/ROLE configuration error (invalid keys, preset guard, etc.)."""


class InspectorError(AgentMigrateError):
    """DB 스키마 조회 실패."""


class MigrationError(AgentMigrateError):
    """마이그레이션 생성/적용 실패."""


class DangerousMigrationError(MigrationError):
    """DANGER 마이그레이션에 --force 없이 시도."""
