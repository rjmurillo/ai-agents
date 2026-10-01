"""The Python Security Checks job runs Bandit even when pip-audit fails.

Issue #6028: pip-audit failed on a transitive pyjwt pin, and the default
success() condition then skipped Bandit on every pull request. Assertions parse
the YAML object graph (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"


def _steps() -> list[dict[str, Any]]:
    document = yaml.safe_load(PYTEST_WORKFLOW.read_text(encoding="utf-8"))
    return list(document["jobs"]["security"]["steps"])


def _step(name: str) -> tuple[int, dict[str, Any]]:
    matches = [(i, step) for i, step in enumerate(_steps()) if step.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


def test_bandit_runs_after_pip_audit() -> None:
    audit_at, _ = _step("Run pip-audit")
    bandit_at, _ = _step("Run Bandit")

    assert audit_at < bandit_at


def test_bandit_does_not_depend_on_the_pip_audit_outcome() -> None:
    _, bandit = _step("Run Bandit")

    assert bandit.get("if") == "${{ !cancelled() }}"


def test_pip_audit_still_fails_the_job() -> None:
    """Negative: running Bandit anyway must not soften the audit itself."""
    _, audit = _step("Run pip-audit")

    assert "continue-on-error" not in audit
    assert "if" not in audit
    assert "|| true" not in str(audit["run"])
