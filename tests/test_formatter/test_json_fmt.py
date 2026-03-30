"""Tests for JSON formatter output."""

from __future__ import annotations

import json
import re

from agent_migrate.formatter.json_fmt import (
    json_auto,
    json_diff,
    json_plan,
    json_rls,
    json_snapshot,
)
from agent_migrate.formatter.ref import RefEngine
from agent_migrate.types import (
    ColumnSchema,
    DBColumnSchema,
    DBRLSPolicy,
    DBRLSStatus,
    DBRoleInfo,
    DBTableSchema,
    DiffItem,
    DiffType,
    MigrationPlan,
    MigrationStep,
    ModelSchema,
    RiskLevel,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _sample_data():
    col = ColumnSchema(name="id", python_type="Integer", nullable=False, primary_key=True)
    model = ModelSchema(name="User", tablename="users", columns=(col,))
    db_col = DBColumnSchema(name="id", data_type="integer", is_nullable=False)
    table = DBTableSchema(name="users", schema_name="public", columns=(db_col,))
    diff = DiffItem(diff_type=DiffType.COLUMN_ADDED, table_name="users", column_name="email")
    ref_map = RefEngine().assign([model], [table])
    return model, table, diff, ref_map


class TestJsonSnapshot:
    def test_valid_json(self) -> None:
        model, table, diff, ref_map = _sample_data()
        out = json_snapshot([model], [table], [diff], ref_map, "test-db")
        data = json.loads(out)
        assert data["v"] == 1
        assert data["cmd"] == "snapshot"
        assert data["drift_count"] == 1

    def test_no_ansi(self) -> None:
        model, table, diff, ref_map = _sample_data()
        out = json_snapshot([model], [table], [diff], ref_map, "test-db")
        assert not _ANSI_RE.search(out)

    def test_enum_serialized(self) -> None:
        model, table, diff, ref_map = _sample_data()
        out = json_snapshot([model], [table], [diff], ref_map, "test-db")
        data = json.loads(out)
        assert data["diffs"][0]["type"] == "column_added"
        assert data["diffs"][0]["risk"] == "safe"


class TestJsonDiff:
    def test_valid_json(self) -> None:
        _, _, diff, ref_map = _sample_data()
        out = json_diff([diff], ref_map)
        data = json.loads(out)
        assert data["cmd"] == "diff"
        assert data["count"] == 1

    def test_empty_diffs(self) -> None:
        _, _, _, ref_map = _sample_data()
        out = json_diff([], ref_map)
        data = json.loads(out)
        assert data["count"] == 0


class TestJsonPlan:
    def test_valid_json(self) -> None:
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN email TEXT;",
            risk=RiskLevel.SAFE,
            description="Add email column",
        )
        plan = MigrationPlan(steps=(step,), overall_risk=RiskLevel.SAFE)
        _, _, _, ref_map = _sample_data()
        out = json_plan(plan, ref_map)
        data = json.loads(out)
        assert data["cmd"] == "plan"
        assert data["step_count"] == 1
        assert data["overall_risk"] == "safe"


class TestJsonRls:
    def test_valid_json(self) -> None:
        status = DBRLSStatus(table_name="users", schema_name="public", rls_enabled=True, rls_forced=False)
        policy = DBRLSPolicy(
            policy_name="users_select_owner", table_name="users", schema_name="public",
            command="SELECT", permissive="PERMISSIVE", roles=("PUBLIC",),
            using_qual="current_user = user_id", with_check_qual=None,
        )
        role = DBRoleInfo(
            role_name="authenticated", is_superuser=False,
            can_login=True, can_create_role=False, can_create_db=False,
        )
        out = json_rls([status], [policy], [role])
        data = json.loads(out)
        assert data["cmd"] == "rls"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["rls"] is True

    def test_no_ansi(self) -> None:
        out = json_rls([], [], [])
        assert not _ANSI_RE.search(out)


class TestJsonAuto:
    def test_in_sync(self) -> None:
        model, table, _, ref_map = _sample_data()
        out = json_auto([model], [table], [], None, ref_map, "test-db")
        data = json.loads(out)
        assert data["in_sync"] is True
        assert data["drift_count"] == 0

    def test_with_diffs(self) -> None:
        model, table, diff, ref_map = _sample_data()
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN email TEXT;",
            risk=RiskLevel.SAFE, description="Add email",
        )
        plan = MigrationPlan(steps=(step,), overall_risk=RiskLevel.SAFE)
        out = json_auto([model], [table], [diff], plan, ref_map, "test-db")
        data = json.loads(out)
        assert data["in_sync"] is False
        assert data["plan"]["step_count"] == 1

    def test_with_generated_file(self) -> None:
        model, table, diff, ref_map = _sample_data()
        out = json_auto(
            [model], [table], [diff], None, ref_map, "test-db",
            generated_file="/path/to/migration.sql",
        )
        data = json.loads(out)
        assert data["generated"] == "/path/to/migration.sql"
