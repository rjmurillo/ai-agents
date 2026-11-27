"""Tests for scripts/ci/collect_excluded_test_bytecode.py."""

from __future__ import annotations

from scripts.ci import collect_excluded_test_bytecode as collector
from scripts.ci import run_pytest_non_tmp
from scripts.ci import run_pytest_partition as runner

EXPECTED_EXCLUDED = [
    "tests/skills/github/test_wait_for_unresolved_zero.py",
    "tests/test_ai_review.py",
    "tests/test_mutation_workspace_signals.py",
    "tests/test_pr_autofix_late_live_state_gate.py",
    "tests/test_quality_gate.py",
    "tests/test_safe_push_pr_branch.py",
    "tests/test_verdict.py",
]


def test_collects_exactly_the_files_outside_the_split_pool(monkeypatch) -> None:
    calls = []

    def collect(args) -> int:
        calls.append(list(args))
        return 0

    monkeypatch.setattr(run_pytest_non_tmp, "main", collect)

    assert collector.main([]) == 0

    assert calls == [[*runner.PYTEST_CONFIG_ARGS, "--collect-only", "-q", *EXPECTED_EXCLUDED]]


def test_a_collection_failure_is_returned(monkeypatch) -> None:
    monkeypatch.setattr(run_pytest_non_tmp, "main", lambda _args: 5)

    assert collector.main([]) == 5
