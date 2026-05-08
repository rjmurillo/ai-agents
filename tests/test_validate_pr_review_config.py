"""Tests for validate_pr_review_config.py schema validation."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validate_pr_review_config import validate_config

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VALIDATOR = _REPO_ROOT / "scripts" / "validate_pr_review_config.py"

VALID_CONFIG: dict = {
    "scripts": {
        "claude_code": {
            "get_pr_context": "python3 script.py",
            "test_pr_merged": "python3 script.py",
            "get_review_threads": "python3 script.py",
            "get_unresolved_threads": "python3 script.py",
            "get_unaddressed_comments": "python3 script.py",
            "get_pr_checks": "python3 script.py",
            "add_thread_reply": "python3 script.py",
            "add_thread_reply_resolve": "python3 script.py",
            "resolve_thread": "python3 script.py",
        },
        "copilot": {
            "get_pr_context": "pwsh script.ps1",
            "test_pr_merged": "pwsh script.ps1",
            "get_review_threads": "pwsh script.ps1",
            "get_unresolved_threads": "pwsh script.ps1",
            "get_unaddressed_comments": "pwsh script.ps1",
            "get_pr_checks": "pwsh script.ps1",
            "add_thread_reply": "pwsh script.ps1",
            "resolve_thread": "pwsh script.ps1",
        },
    },
    "check_failure_actions": [
        {"check_type": "Tests", "action": "Run locally"},
    ],
    "error_recovery": [
        {"scenario": "PR not found", "action": "Skip"},
    ],
    "completion_criteria": [
        {
            "name": "All comments addressed",
            "verification": "command",
            "command": "python3 script.py --pull-request {pr}",
            "pass_when": "stdout-json.unresolved_count == 0",
            "fail_open": False,
        },
    ],
    "failure_handling": [
        {"type": "Merge conflicts", "action": "Resolve"},
    ],
    "worktree_constraints": [
        "Changes must be in worktree",
    ],
    "related_memories": [
        {"name": "pr-review-007", "purpose": "Merge state verification"},
    ],
    "thread_resolution": {
        "note": "Replying does not resolve threads.",
        "batch_graphql_template": "mutation { ... }",
    },
    "invocation_limits": {
        "all_open_max_prs": 5,
        "all_open_overflow_action": "Report count of skipped PRs",
        "completion_gate_max_retries": 3,
        "completion_gate_overflow_action": "Escalate to user",
    },
    "output_constraints": {
        "per_pr_max_response_tokens": 4096,
        "summary_format": "table",
        "summary_format_allowed_values": ["table"],
        "summary_required_columns": ["PR", "Branch", "Status"],
    },
}


class TestValidateConfig:
    def test_valid_config_passes(self) -> None:
        errors = validate_config(VALID_CONFIG)
        assert errors == []

    def test_missing_top_level_key(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["scripts"]
        errors = validate_config(config)
        assert any("Missing required top-level key: scripts" in e for e in errors)

    def test_missing_scripts_section(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["scripts"]["copilot"]
        errors = validate_config(config)
        assert any("Missing scripts section: copilot" in e for e in errors)

    def test_missing_script_key(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["scripts"]["claude_code"]["test_pr_merged"]
        errors = validate_config(config)
        assert any("test_pr_merged" in e for e in errors)

    def test_missing_completion_criteria_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["completion_criteria"][0]["name"]
        errors = validate_config(config)
        assert any("completion_criteria[0] missing field: name" in e for e in errors)

    def test_missing_completion_criteria_pass_when(self) -> None:
        # Either pass_when or pass_when_python must be present.
        config = copy.deepcopy(VALID_CONFIG)
        del config["completion_criteria"][0]["pass_when"]
        errors = validate_config(config)
        assert any(
            "completion_criteria[0] missing field: pass_when" in e
            for e in errors
        )

    def test_completion_criteria_pass_when_python_accepted(self) -> None:
        # pass_when_python is the documented escape hatch when the DSL is
        # too narrow; using it instead of pass_when must validate cleanly.
        config = copy.deepcopy(VALID_CONFIG)
        del config["completion_criteria"][0]["pass_when"]
        config["completion_criteria"][0]["pass_when_python"] = (
            "lambda d: d.get('x', 0) == 0"
        )
        errors = validate_config(config)
        assert errors == []

    def test_completion_criteria_both_pass_when_fields_rejected(self) -> None:
        # Per Copilot review: both-set is ambiguous because the
        # dispatcher silently picks pass_when_python first. The
        # validator must reject it before runtime.
        config = copy.deepcopy(VALID_CONFIG)
        config["completion_criteria"][0]["pass_when_python"] = (
            "lambda d: True"
        )
        errors = validate_config(config)
        assert any(
            "both pass_when and pass_when_python" in e for e in errors
        )

    def test_completion_criteria_null_pass_when_rejected(self) -> None:
        # YAML `pass_when:` with no value yields None. The key exists
        # but the value is falsy. The validator must reject this so it
        # matches the dispatcher's truthiness check (bug fix).
        config = copy.deepcopy(VALID_CONFIG)
        config["completion_criteria"][0]["pass_when"] = None
        errors = validate_config(config)
        assert any(
            "completion_criteria[0] missing field: pass_when" in e
            for e in errors
        )

    def test_completion_criteria_empty_pass_when_rejected(self) -> None:
        # YAML `pass_when: ""` yields an empty string. The key exists
        # but the value is falsy. The validator must reject this so it
        # matches the dispatcher's truthiness check (bug fix).
        config = copy.deepcopy(VALID_CONFIG)
        config["completion_criteria"][0]["pass_when"] = ""
        errors = validate_config(config)
        assert any(
            "completion_criteria[0] missing field: pass_when" in e
            for e in errors
        )

    def test_completion_criteria_verification_must_be_command(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["completion_criteria"][0]["verification"] = "narrative"
        errors = validate_config(config)
        assert any(
            "completion_criteria[0].verification must be 'command'" in e
            for e in errors
        )

    def test_completion_criteria_fail_open_must_be_bool(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["completion_criteria"][0]["fail_open"] = "yes"
        errors = validate_config(config)
        assert any(
            "completion_criteria[0].fail_open must be a boolean" in e
            for e in errors
        )

    def test_missing_error_recovery_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["error_recovery"][0]["action"]
        errors = validate_config(config)
        assert any("error_recovery[0] missing field: action" in e for e in errors)

    def test_worktree_constraints_must_be_list(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["worktree_constraints"] = "not a list"
        errors = validate_config(config)
        assert any("worktree_constraints must be a list" in e for e in errors)

    def test_empty_worktree_constraints(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["worktree_constraints"] = []
        errors = validate_config(config)
        assert any("worktree_constraints must not be empty" in e for e in errors)

    def test_missing_thread_resolution_note(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["thread_resolution"]["note"]
        errors = validate_config(config)
        assert any("thread_resolution missing field: note" in e for e in errors)

    def test_missing_related_memory_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["related_memories"][0]["purpose"]
        errors = validate_config(config)
        assert any("related_memories[0] missing field: purpose" in e for e in errors)

    def test_missing_check_failure_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["check_failure_actions"][0]["check_type"]
        errors = validate_config(config)
        assert any("check_failure_actions[0] missing field: check_type" in e for e in errors)

    def test_missing_failure_handling_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["failure_handling"][0]["type"]
        errors = validate_config(config)
        assert any("failure_handling[0] missing field: type" in e for e in errors)

    def test_missing_add_thread_reply(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["scripts"]["claude_code"]["add_thread_reply"]
        errors = validate_config(config)
        assert any("add_thread_reply" in e for e in errors)

    def test_missing_add_thread_reply_resolve_claude_code_only(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["scripts"]["claude_code"]["add_thread_reply_resolve"]
        errors = validate_config(config)
        # Should fail for claude_code
        assert any("add_thread_reply_resolve" in e for e in errors)
        # Copilot section doesn't need this key
        assert not any("copilot" in e and "add_thread_reply_resolve" in e for e in errors)

    def test_missing_invocation_limits_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["invocation_limits"]["all_open_max_prs"]
        errors = validate_config(config)
        assert any("invocation_limits missing field: all_open_max_prs" in e for e in errors)

    def test_missing_output_constraints_field(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["output_constraints"]["summary_format"]
        errors = validate_config(config)
        assert any("output_constraints missing field: summary_format" in e for e in errors)

    def test_output_constraints_columns_must_be_nonempty_list(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_required_columns"] = []
        errors = validate_config(config)
        assert any(
            "summary_required_columns must be a non-empty list of non-empty strings"
            in e
            for e in errors
        )

    def test_missing_invocation_limits_top_level(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["invocation_limits"]
        errors = validate_config(config)
        assert any("Missing required top-level key: invocation_limits" in e for e in errors)

    def test_missing_output_constraints_top_level(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        del config["output_constraints"]
        errors = validate_config(config)
        assert any("Missing required top-level key: output_constraints" in e for e in errors)

    # --- Hardening: type guards and value-range checks (CodeRabbit feedback) ---

    def test_invocation_limits_must_be_mapping(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"] = None
        errors = validate_config(config)
        assert any("invocation_limits must be a mapping" in e for e in errors)

    def test_output_constraints_must_be_mapping(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"] = None
        errors = validate_config(config)
        assert any("output_constraints must be a mapping" in e for e in errors)

    def test_all_open_max_prs_must_be_positive_int(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["all_open_max_prs"] = 0
        errors = validate_config(config)
        assert any("all_open_max_prs must be an integer >= 1" in e for e in errors)

    def test_all_open_max_prs_rejects_string(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["all_open_max_prs"] = "5"
        errors = validate_config(config)
        assert any("all_open_max_prs must be an integer >= 1" in e for e in errors)

    def test_completion_gate_max_retries_rejects_negative(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["completion_gate_max_retries"] = -1
        errors = validate_config(config)
        assert any("completion_gate_max_retries must be an integer >= 0" in e for e in errors)

    def test_overflow_action_must_be_nonempty_string(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["all_open_overflow_action"] = "  "
        errors = validate_config(config)
        assert any(
            "all_open_overflow_action must be a non-empty string" in e for e in errors
        )

    def test_per_pr_max_response_tokens_rejects_zero(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["per_pr_max_response_tokens"] = 0
        errors = validate_config(config)
        assert any("per_pr_max_response_tokens must be an integer >= 1" in e for e in errors)

    def test_summary_format_rejects_empty_string(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_format"] = ""
        errors = validate_config(config)
        assert any("summary_format must be a non-empty string" in e for e in errors)

    def test_summary_format_allowed_values_rejects_empty_list(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_format_allowed_values"] = []
        errors = validate_config(config)
        assert any(
            "summary_format_allowed_values must be a non-empty list of non-empty strings"
            in e
            for e in errors
        )

    def test_summary_format_allowed_values_rejects_non_string_entry(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_format_allowed_values"] = ["table", 42]
        errors = validate_config(config)
        assert any(
            "summary_format_allowed_values must be a non-empty list of non-empty strings"
            in e
            for e in errors
        )

    def test_summary_format_must_be_in_allowed_values(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_format"] = "json"
        config["output_constraints"]["summary_format_allowed_values"] = ["table"]
        errors = validate_config(config)
        assert any(
            "summary_format must be one of summary_format_allowed_values" in e
            for e in errors
        )

    def test_summary_required_columns_rejects_non_string_entry(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_required_columns"] = ["PR", 0, "Branch"]
        errors = validate_config(config)
        assert any(
            "summary_required_columns must be a non-empty list of non-empty strings"
            in e
            for e in errors
        )

    def test_summary_required_columns_rejects_blank_entry(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["summary_required_columns"] = ["PR", "  ", "Branch"]
        errors = validate_config(config)
        assert any(
            "summary_required_columns must be a non-empty list of non-empty strings"
            in e
            for e in errors
        )

    # --- bool-as-int regression guards ---
    # Python's `bool` is a subclass of `int`, so `isinstance(True, int)` is
    # True. The validator excludes `bool` explicitly; these tests pin that.

    def test_all_open_max_prs_rejects_bool(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["all_open_max_prs"] = True
        errors = validate_config(config)
        assert any("all_open_max_prs must be an integer >= 1" in e for e in errors)

    def test_completion_gate_max_retries_rejects_bool(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["invocation_limits"]["completion_gate_max_retries"] = False
        errors = validate_config(config)
        assert any(
            "completion_gate_max_retries must be an integer >= 0" in e for e in errors
        )

    def test_per_pr_max_response_tokens_rejects_bool(self) -> None:
        config = copy.deepcopy(VALID_CONFIG)
        config["output_constraints"]["per_pr_max_response_tokens"] = True
        errors = validate_config(config)
        assert any(
            "per_pr_max_response_tokens must be an integer >= 1" in e for e in errors
        )


class TestPathValidationHardening:
    """CWE-22 / null-byte / control-character coverage on the safe-path helper.

    Subprocess argv cannot carry an embedded null byte (the OS rejects it
    before Python sees it), so null-byte and control-character cases call
    ``validate_safe_path`` directly. Path traversal and absolute-outside-root
    cases are covered by ``TestCliPathSafety`` below, which exercises the CLI
    end to end.
    """

    def test_null_byte_in_path_rejected(self) -> None:
        from scripts.utils.path_validation import validate_safe_path

        with pytest.raises(ValueError):
            validate_safe_path("config\x00.yaml", _REPO_ROOT)

    def test_null_byte_in_subdirectory_rejected(self) -> None:
        from scripts.utils.path_validation import validate_safe_path

        with pytest.raises(ValueError):
            validate_safe_path("scripts/\x00config.yaml", _REPO_ROOT)

    def test_traversal_via_validate_safe_path_rejected(self) -> None:
        from scripts.utils.path_validation import validate_safe_path

        with pytest.raises(ValueError):
            validate_safe_path("../../etc/passwd", _REPO_ROOT)

    def test_absolute_outside_root_via_validate_safe_path_rejected(self) -> None:
        from scripts.utils.path_validation import validate_safe_path

        with pytest.raises(ValueError):
            validate_safe_path("/etc/passwd", _REPO_ROOT)

    def test_control_chars_rejected_by_cli(self) -> None:
        """Control chars resolve to a path that does not exist; CLI returns 2."""
        # newline-bearing input: validate_safe_path resolves it, but the
        # resulting file does not exist, so the CLI rejects with exit 2.
        result = subprocess.run(
            [sys.executable, str(_VALIDATOR), "config\r.yaml"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 2
        # Either "Invalid config path" (from validate_safe_path) or
        # "Config file not found" is acceptable; both signal rejection.
        assert (
            "Invalid config path" in result.stderr
            or "Config file not found" in result.stderr
        )


class TestCliPathSafety:
    """CWE-22 path-traversal guards on the CLI entry point."""

    def _run(self, *argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(_VALIDATOR), *argv],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )

    def test_path_traversal_rejected(self) -> None:
        result = self._run("../../etc/passwd")
        assert result.returncode == 2
        assert "Invalid config path" in result.stderr

    def test_absolute_outside_root_rejected(self) -> None:
        result = self._run("/etc/passwd")
        assert result.returncode == 2
        assert "Invalid config path" in result.stderr

    def test_default_path_accepted(self) -> None:
        result = self._run()
        assert result.returncode == 0
        assert "valid" in result.stdout
