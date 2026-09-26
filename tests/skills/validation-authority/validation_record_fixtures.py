"""Shared decision-record builders for the validation-authority tests (issue #5387)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/validation-authority/scripts/validation_record.py",
    module_name="test_validation_record_mod",
)


def _merged(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge top-level keys, and merge `provenance`/`authority` one level deep."""
    result = dict(base)
    provenance_overrides = overrides.pop("provenance", None)
    authority_overrides = overrides.pop("authority", None)
    result.update(overrides)
    if provenance_overrides:
        result["provenance"] = {**result["provenance"], **provenance_overrides}
    if authority_overrides:
        result["authority"] = {**result["authority"], **authority_overrides}
    return result


def make_target(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "target": "scripts/validation/check_x.py",
        "component": "check_x validator",
        "provenance": {
            "category": "LOCAL",
            "owner": "policy team",
            "evidence": "file header names the policy team as the owner",
        },
        "authority": {
            "contract": "exit 0 pass, 1 defects, 2 config error (ADR-035)",
            "diagnosis": "implementation-defect",
            "permitted_change_location": "scripts/validation/check_x.py",
        },
    }
    return _merged(base, overrides)


def make_local_config_target(**overrides: Any) -> dict[str, Any]:
    base = make_target(
        target=".markdownlint-cli2.yaml",
        component="markdownlint config",
        authority={
            "diagnosis": "local-config-defect",
            "permitted_change_location": ".markdownlint-cli2.yaml",
        },
    )
    return _merged(base, overrides)


def make_generated_target(**overrides: Any) -> dict[str, Any]:
    base = make_target(
        target="src/claude/skills/x/scripts/check_x.py",
        component="check_x validator (generated mirror)",
        provenance={
            "category": "GENERATED",
            "canonical_source": ".claude/skills/x/scripts/check_x.py",
        },
        authority={
            "diagnosis": "stale-generated-output",
            "permitted_change_location": ".claude/skills/x/scripts/check_x.py",
        },
    )
    return _merged(base, overrides)


def make_vendor_target(**overrides: Any) -> dict[str, Any]:
    base = make_target(
        target="vendor/lint/rule.py",
        component="vendored lint rule",
        provenance={"category": "VENDOR", "owner": "upstream vendor"},
        authority={
            "diagnosis": "implementation-defect",
            "permitted_change_location": "vendor/lint/rule.py.local-override",
        },
    )
    return _merged(base, overrides)


def make_upstream_target(**overrides: Any) -> dict[str, Any]:
    base = make_target(
        target="node_modules/eslint/lib/rule.js",
        component="eslint core rule",
        provenance={"category": "UPSTREAM", "owner": "eslint maintainers"},
        authority={
            "diagnosis": "upstream-defect",
            "permitted_change_location": ".eslintrc",
            "escalation": "filed https://github.com/eslint/eslint/issues/00000",
        },
    )
    return _merged(base, overrides)


def make_unknown_owner_target(**overrides: Any) -> dict[str, Any]:
    base = make_target(provenance={"category": "UNKNOWN", "owner": "", "evidence": ""})
    return _merged(base, overrides)


def make_baseline_target(policy_source: str, **overrides: Any) -> dict[str, Any]:
    base = make_target(
        target="scripts/validation/coverage_baseline.json",
        component="coverage baseline",
        authority={"diagnosis": "baseline-update"},
    )
    base["baseline_justification"] = {
        "policy_source": policy_source,
        "reason": "New modules landed with full coverage; extending the ratchet.",
        "added_entries": [{"path": "new_module.py", "justification": "100% covered on merge"}],
    }
    return _merged(base, overrides)


def make_record(*targets: Any, trigger: Any = None) -> dict[str, Any]:
    return {
        "trigger": trigger if trigger is not None else {"decision": "activate"},
        "targets": list(targets),
    }


def record_errors(
    record: Any,
    changed_paths: tuple[str, ...] = (),
    repo_root: Path | None = None,
    trigger_module: Any = None,
) -> list[str]:
    errors: list[str] = mod.validate(record, changed_paths, repo_root, trigger_module)
    return errors
