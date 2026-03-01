"""Tests for validate_pr_review_config.py schema validation."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.validate_pr_review_config import validate_config

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
        {"criterion": "All comments addressed", "verification": "Check threads", "required": True},
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
        del config["completion_criteria"][0]["required"]
        errors = validate_config(config)
        assert any("completion_criteria[0] missing field: required" in e for e in errors)

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
