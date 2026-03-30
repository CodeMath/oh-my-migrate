"""Tests for RawSQLGenerator file output."""

from __future__ import annotations

import re

from agent_migrate.migration.raw_sql import RawSQLGenerator, _checksum, _slug
from agent_migrate.types import MigrationPlan, MigrationStep, RiskLevel

# ── Helpers ───────────────────────────────────────────────────────────────────


def _plan(*steps: tuple[str, str | None]) -> MigrationPlan:
    """Build a MigrationPlan from (sql, rollback_sql) tuples."""
    migration_steps = tuple(
        MigrationStep(
            sql=sql,
            risk=RiskLevel.SAFE,
            description="test",
            rollback_sql=rollback,
        )
        for sql, rollback in steps
    )
    return MigrationPlan(steps=migration_steps, overall_risk=RiskLevel.SAFE)


# ── _slug helper ──────────────────────────────────────────────────────────────


def test_slug_lowercases_and_replaces_spaces():
    assert _slug("Add user table") == "add_user_table"


def test_slug_truncates_to_50():
    long = "a" * 100
    assert len(_slug(long)) == 50


def test_slug_strips_leading_trailing_underscores():
    assert not _slug("  hello  ").startswith("_")


# ── File creation ─────────────────────────────────────────────────────────────


def test_generates_sql_file_in_output_dir(tmp_path):
    gen = RawSQLGenerator(tmp_path / "migrations")
    plan = _plan(('CREATE TABLE "t1" ("id" SERIAL PRIMARY KEY);', None))
    filepath = gen.generate(plan, "create t1")

    assert filepath.exists()
    assert filepath.suffix == ".sql"
    assert "create_t1" in filepath.name


def test_output_dir_created_if_missing(tmp_path):
    output_dir = tmp_path / "deep" / "migrations"
    gen = RawSQLGenerator(output_dir)
    plan = _plan(('CREATE TABLE "t1" ("id" SERIAL PRIMARY KEY);', None))
    gen.generate(plan, "test")
    assert output_dir.exists()


def test_filename_has_timestamp_prefix(tmp_path):
    gen = RawSQLGenerator(tmp_path)
    plan = _plan(('SELECT 1;', None))
    filepath = gen.generate(plan, "test migration")
    # Filename starts with a 14-digit timestamp
    assert re.match(r"^\d{14}_", filepath.name)


# ── File content ──────────────────────────────────────────────────────────────


def test_file_contains_upgrade_sql(tmp_path):
    sql = 'CREATE TABLE "users" ("id" SERIAL PRIMARY KEY);'
    gen = RawSQLGenerator(tmp_path)
    filepath = gen.generate(_plan((sql, None)), "add users")
    content = filepath.read_text()
    assert sql in content
    assert "UPGRADE" in content


def test_file_contains_rollback_as_comments(tmp_path):
    upgrade_sql = 'ALTER TABLE "users" ADD COLUMN "bio" TEXT;'
    rollback_sql = 'ALTER TABLE "users" DROP COLUMN "bio";'
    gen = RawSQLGenerator(tmp_path)
    filepath = gen.generate(_plan((upgrade_sql, rollback_sql)), "add bio")
    content = filepath.read_text()
    assert "ROLLBACK" in content
    assert f"-- {rollback_sql}" in content


def test_file_has_checksum_header(tmp_path):
    sql = 'SELECT 1;'
    gen = RawSQLGenerator(tmp_path)
    filepath = gen.generate(_plan((sql, None)), "test")
    content = filepath.read_text()
    expected_checksum = _checksum(sql)
    assert f"-- Checksum: {expected_checksum}" in content


def test_file_has_migration_message_header(tmp_path):
    gen = RawSQLGenerator(tmp_path)
    filepath = gen.generate(_plan(('SELECT 1;', None)), "my migration message")
    content = filepath.read_text()
    assert "-- Migration: my migration message" in content


def test_empty_plan_generates_file_with_headers_only(tmp_path):
    gen = RawSQLGenerator(tmp_path)
    plan = MigrationPlan(steps=(), overall_risk=RiskLevel.SAFE)
    filepath = gen.generate(plan, "empty")
    content = filepath.read_text()
    assert "-- Migration: empty" in content
    assert "UPGRADE" in content
    # No rollback section when there are no rollback steps
    assert "ROLLBACK" not in content


def test_no_rollback_section_when_all_steps_have_no_rollback(tmp_path):
    gen = RawSQLGenerator(tmp_path)
    plan = _plan(('DROP TABLE "t1";', None))
    filepath = gen.generate(plan, "drop t1")
    content = filepath.read_text()
    assert "ROLLBACK" not in content
