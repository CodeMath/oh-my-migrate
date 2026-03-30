"""Preset resolver: converts __rls__ dict values into RLSPolicySchema instances."""

from __future__ import annotations

from agent_migrate.exceptions import ConfigError
from agent_migrate.rls.presets import (
    PG_NATIVE_PRESETS,
    SUPABASE_PRESETS,
    get_presets,
)
from agent_migrate.types import VALID_RLS_COMMANDS, RLSCommand, RLSPolicySchema


class PresetResolver:
    """Resolve __rls__ dict values into RLSPolicySchema instances."""

    def resolve(
        self,
        table_name: str,
        rls_dict: dict[str, str],
        *,
        is_supabase: bool = False,
        owner_column: str = "user_id",
    ) -> list[RLSPolicySchema]:
        """Convert preset names to full RLSPolicySchema objects.

        Key validation: only VALID_RLS_COMMANDS keys are accepted.
        Supabase guard: if preset.requires_supabase and not is_supabase, raise ConfigError.
        Policy naming: {table}_{command}_{preset_name}
        """
        invalid_keys = set(rls_dict.keys()) - VALID_RLS_COMMANDS
        if invalid_keys:
            raise ConfigError(
                f"Invalid __rls__ keys for table {table_name!r}: {invalid_keys}. "
                f"Allowed: {sorted(VALID_RLS_COMMANDS)}"
            )

        presets = get_presets(is_supabase)
        policies: list[RLSPolicySchema] = []

        for command_str, preset_name in rls_dict.items():
            if preset_name not in presets:
                other_presets = SUPABASE_PRESETS if not is_supabase else PG_NATIVE_PRESETS
                if preset_name in other_presets and other_presets[preset_name].requires_supabase:
                    raise ConfigError(
                        f"Preset {preset_name!r} requires Supabase but current environment "
                        f"is vanilla PostgreSQL. Use a PG-native preset or set supabase=true "
                        f"in pyproject.toml."
                    )
                raise ConfigError(
                    f"Unknown RLS preset {preset_name!r} for table {table_name!r}"
                )

            preset = presets[preset_name]
            if preset.requires_supabase and not is_supabase:
                raise ConfigError(
                    f"Preset {preset_name!r} requires Supabase (uses auth.uid()/auth.role()) "
                    f"but Supabase was not detected. Set supabase=true in pyproject.toml "
                    f"or use a PostgreSQL-native preset."
                )

            policy_name = f"{table_name}_{command_str}_{preset_name}"

            resolved_using = preset.using_template.replace(
                "{owner_column}", owner_column
            ).replace("{table}", table_name)

            resolved_check: str | None = None
            if preset.with_check_template:
                resolved_check = preset.with_check_template.replace(
                    "{owner_column}", owner_column
                ).replace("{table}", table_name)

            rls_command = RLSCommand[command_str.upper()]
            if rls_command == RLSCommand.ALL:
                # "all" expands to individual commands
                for cmd in (
                    RLSCommand.SELECT, RLSCommand.INSERT,
                    RLSCommand.UPDATE, RLSCommand.DELETE,
                ):
                    all_policy_name = f"{table_name}_{cmd.value.lower()}_{preset_name}"
                    policies.append(
                        RLSPolicySchema(
                            name=all_policy_name,
                            table_name=table_name,
                            command=cmd,
                            using_expr=resolved_using,
                            with_check_expr=resolved_check,
                            role=preset.requires_role or "PUBLIC",
                            permissive=True,
                        )
                    )
            else:
                policies.append(
                    RLSPolicySchema(
                        name=policy_name,
                        table_name=table_name,
                        command=rls_command,
                        using_expr=resolved_using,
                        with_check_expr=resolved_check,
                        role=preset.requires_role or "PUBLIC",
                        permissive=True,
                    )
                )

        return policies
