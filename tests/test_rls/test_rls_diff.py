"""Tests for RLS diff engine, risk analyzer, formatter coverage, and planner."""

from __future__ import annotations

from agent_migrate.diff.engine import DiffEngine
from agent_migrate.diff.risk import RiskAnalyzer
from agent_migrate.formatter.diff_fmt import _DIFF_STYLE
from agent_migrate.migration.planner import _STEP_ORDER, MigrationPlanner
from agent_migrate.types import (
    DBRLSPolicy,
    DBRLSStatus,
    DiffItem,
    DiffType,
    ModelSchema,
    RiskLevel,
    RLSCommand,
    RLSPolicySchema,
)


class TestExhaustiveDiffTypeCoverage:
    def test_all_diff_types_have_risk_rules(self) -> None:
        analyzer = RiskAnalyzer()
        for dt in DiffType:
            item = DiffItem(
                diff_type=dt, table_name="test_table",
                model_value="test", db_value="test",
            )
            results = analyzer.analyze([item])
            assert len(results) == 1, f"No result for {dt}"
            assert results[0].risk is not None, f"No risk for {dt}"

    def test_all_diff_types_have_formatter_entries(self) -> None:
        for dt in DiffType:
            assert dt in _DIFF_STYLE, (
                f"DiffType {dt.name} missing from _DIFF_STYLE"
            )

    def test_all_diff_types_have_step_order(self) -> None:
        for dt in DiffType:
            assert dt in _STEP_ORDER, (
                f"DiffType {dt.name} missing from _STEP_ORDER"
            )

    def test_no_diff_type_falls_through_to_unknown_symbol(self) -> None:
        for dt in DiffType:
            symbol, _ = _DIFF_STYLE.get(dt, ("[?]", False))
            assert symbol != "[?]", f"DiffType {dt.name} falls through to [?]"


class TestRLSDiffEngine:
    def _make_model(
        self,
        tablename: str,
        rls_policies: tuple[RLSPolicySchema, ...] = (),
        rls_opt_out: bool = False,
    ) -> ModelSchema:
        return ModelSchema(
            name=tablename.title(),
            tablename=tablename,
            columns=(),
            rls_policies=rls_policies,
            rls_opt_out=rls_opt_out,
        )

    def _make_policy(self, name: str, table: str) -> RLSPolicySchema:
        return RLSPolicySchema(
            name=name, table_name=table,
            command=RLSCommand.SELECT,
            using_expr="current_user = user_id",
        )

    def _make_db_policy(self, name: str, table: str) -> DBRLSPolicy:
        return DBRLSPolicy(
            policy_name=name, table_name=table, schema_name="public",
            command="SELECT", permissive="PERMISSIVE",
            roles=("PUBLIC",),
            using_qual="current_user = user_id",
            with_check_qual=None,
        )

    def test_rls_enabled_changed(self) -> None:
        model = self._make_model(
            "posts", rls_policies=(self._make_policy("p", "posts"),)
        )
        status = DBRLSStatus(
            table_name="posts", schema_name="public",
            rls_enabled=False, rls_forced=False,
        )
        diffs = DiffEngine().compute_rls_diff([model], [status], [])
        types = [d.diff_type for d in diffs]
        assert DiffType.RLS_ENABLED_CHANGED in types

    def test_rls_policy_added(self) -> None:
        policy = self._make_policy("posts_select_owner", "posts")
        model = self._make_model("posts", rls_policies=(policy,))
        status = DBRLSStatus(
            table_name="posts", schema_name="public",
            rls_enabled=True, rls_forced=False,
        )
        diffs = DiffEngine().compute_rls_diff([model], [status], [])
        types = [d.diff_type for d in diffs]
        assert DiffType.RLS_POLICY_ADDED in types

    def test_rls_policy_removed(self) -> None:
        model = self._make_model(
            "posts",
            rls_policies=(self._make_policy("posts_select_owner", "posts"),),
        )
        db_policy = self._make_db_policy("posts_old_policy", "posts")
        status = DBRLSStatus(
            table_name="posts", schema_name="public",
            rls_enabled=True, rls_forced=False,
        )
        diffs = DiffEngine().compute_rls_diff([model], [status], [db_policy])
        types = [d.diff_type for d in diffs]
        assert DiffType.RLS_POLICY_REMOVED in types

    def test_rls_policy_changed(self) -> None:
        model_policy = RLSPolicySchema(
            name="posts_select_owner", table_name="posts",
            command=RLSCommand.SELECT,
            using_expr="auth.uid() = user_id",
        )
        model = self._make_model("posts", rls_policies=(model_policy,))
        db_policy = DBRLSPolicy(
            policy_name="posts_select_owner", table_name="posts",
            schema_name="public", command="SELECT",
            permissive="PERMISSIVE", roles=("PUBLIC",),
            using_qual="current_user = owner_id",
            with_check_qual=None,
        )
        status = DBRLSStatus(
            table_name="posts", schema_name="public",
            rls_enabled=True, rls_forced=False,
        )
        diffs = DiffEngine().compute_rls_diff([model], [status], [db_policy])
        types = [d.diff_type for d in diffs]
        assert DiffType.RLS_POLICY_CHANGED in types

    def test_rls_policy_untracked(self) -> None:
        model = self._make_model("posts")
        db_policy = self._make_db_policy("posts_some_policy", "posts")
        diffs = DiffEngine().compute_rls_diff([model], [], [db_policy])
        types = [d.diff_type for d in diffs]
        assert DiffType.RLS_POLICY_UNTRACKED in types

    def test_rls_opt_out_skips_diff(self) -> None:
        model = self._make_model("posts", rls_opt_out=True)
        db_policy = self._make_db_policy("posts_policy", "posts")
        diffs = DiffEngine().compute_rls_diff([model], [], [db_policy])
        assert len(diffs) == 0

    def test_db_only_table_policies_ignored(self) -> None:
        db_policy = self._make_db_policy("orphan_policy", "orphan_table")
        diffs = DiffEngine().compute_rls_diff([], [], [db_policy])
        assert len(diffs) == 0

    def test_model_value_stores_policy_name(self) -> None:
        policy = self._make_policy("posts_select_owner", "posts")
        model = self._make_model("posts", rls_policies=(policy,))
        status = DBRLSStatus(
            table_name="posts", schema_name="public",
            rls_enabled=True, rls_forced=False,
        )
        diffs = DiffEngine().compute_rls_diff([model], [status], [])
        added = [d for d in diffs if d.diff_type == DiffType.RLS_POLICY_ADDED]
        assert added[0].model_value == "posts_select_owner"


class TestRLSRiskAnalyzer:
    def _item(self, dt: DiffType) -> DiffItem:
        return DiffItem(
            diff_type=dt, table_name="t",
            model_value="test", db_value="test",
        )

    def test_rls_enabled_changed_danger(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.RLS_ENABLED_CHANGED)])
        assert result[0].risk == RiskLevel.DANGER

    def test_rls_policy_added_caution(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.RLS_POLICY_ADDED)])
        assert result[0].risk == RiskLevel.CAUTION

    def test_rls_policy_removed_danger(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.RLS_POLICY_REMOVED)])
        assert result[0].risk == RiskLevel.DANGER

    def test_rls_policy_changed_danger(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.RLS_POLICY_CHANGED)])
        assert result[0].risk == RiskLevel.DANGER

    def test_rls_policy_untracked_caution(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.RLS_POLICY_UNTRACKED)])
        assert result[0].risk == RiskLevel.CAUTION

    def test_role_missing_danger(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.ROLE_MISSING)])
        assert result[0].risk == RiskLevel.DANGER

    def test_grant_added_caution(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.GRANT_ADDED)])
        assert result[0].risk == RiskLevel.CAUTION

    def test_grant_removed_danger(self) -> None:
        result = RiskAnalyzer().analyze([self._item(DiffType.GRANT_REMOVED)])
        assert result[0].risk == RiskLevel.DANGER


class TestRLSMigrationPlanner:
    def test_rls_enable_generates_sql(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.RLS_ENABLED_CHANGED,
            table_name="posts",
            model_value="enabled", db_value="disabled",
        )
        plan = MigrationPlanner().plan([diff])
        assert len(plan.steps) == 1
        assert "ENABLE ROW LEVEL SECURITY" in plan.steps[0].sql
        assert plan.steps[0].rollback_sql is not None

    def test_rls_policy_add_generates_create_policy(self) -> None:
        policy = RLSPolicySchema(
            name="posts_select_owner", table_name="posts",
            command=RLSCommand.SELECT,
            using_expr="current_user = user_id",
        )
        model = ModelSchema(
            name="Post", tablename="posts", columns=(),
            rls_policies=(policy,),
        )
        diff = DiffItem(
            diff_type=DiffType.RLS_POLICY_ADDED,
            table_name="posts", model_value="posts_select_owner",
        )
        plan = MigrationPlanner().plan([diff], [model])
        assert len(plan.steps) == 1
        assert "CREATE POLICY" in plan.steps[0].sql
        assert "posts_select_owner" in plan.steps[0].sql

    def test_rls_policy_remove_generates_drop(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.RLS_POLICY_REMOVED,
            table_name="posts", model_value="posts_old_policy",
        )
        plan = MigrationPlanner().plan([diff])
        assert len(plan.steps) == 1
        assert "DROP POLICY" in plan.steps[0].sql

    def test_rls_untracked_generates_no_step(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.RLS_POLICY_UNTRACKED, table_name="posts",
        )
        plan = MigrationPlanner().plan([diff])
        assert len(plan.steps) == 0

    def test_role_missing_generates_create_role(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.ROLE_MISSING,
            table_name="posts", model_value="app_user",
        )
        plan = MigrationPlanner().plan([diff])
        assert "CREATE ROLE" in plan.steps[0].sql

    def test_grant_add_generates_grant(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.GRANT_ADDED,
            table_name="posts", model_value="app_user:SELECT",
        )
        plan = MigrationPlanner().plan([diff])
        assert "GRANT SELECT" in plan.steps[0].sql

    def test_grant_remove_generates_revoke(self) -> None:
        diff = DiffItem(
            diff_type=DiffType.GRANT_REMOVED,
            table_name="posts", db_value="old_role:INSERT",
        )
        plan = MigrationPlanner().plan([diff])
        assert "REVOKE INSERT" in plan.steps[0].sql

    def test_step_order_rls_after_schema(self) -> None:
        assert _STEP_ORDER[DiffType.RLS_ENABLED_CHANGED] > _STEP_ORDER[DiffType.TABLE_REMOVED]
        assert _STEP_ORDER[DiffType.RLS_POLICY_ADDED] > _STEP_ORDER[DiffType.RLS_ENABLED_CHANGED]

    def test_step_order_untracked_is_informational(self) -> None:
        assert _STEP_ORDER[DiffType.RLS_POLICY_UNTRACKED] == -1
