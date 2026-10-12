"""The Python Security Checks job runs Bandit even when pip-audit fails.

Issue #6028: pip-audit failed on a transitive pyjwt pin, and the default
success() condition then skipped Bandit on every pull request. Assertions parse
the YAML object graph (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
UV_LOCK = REPO_ROOT / "uv.lock"

# CVE-2026-4539 affects pygments before 2.20.0 (issue #5224).
PYGMENTS_FIXED_IN = (2, 20, 0)


def _steps() -> list[dict[str, Any]]:
    document = yaml.safe_load(PYTEST_WORKFLOW.read_text(encoding="utf-8"))
    return list(document["jobs"]["security"]["steps"])


def _step(name: str) -> tuple[int, dict[str, Any]]:
    matches = [(i, step) for i, step in enumerate(_steps()) if step.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


def _locked_version(package: str) -> tuple[int, ...]:
    document = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    matches = [p for p in document["package"] if p["name"] == package]
    assert len(matches) == 1, f"expected one {package!r} in uv.lock, found {len(matches)}"
    return tuple(int(part) for part in matches[0]["version"].split("."))


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


def _audit_commands() -> list[str]:
    _, audit = _step("Run pip-audit")
    return [
        line.strip()
        for line in str(audit["run"]).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_pip_audit_does_not_ignore_the_fixed_pygments_cve() -> None:
    """Issue #5224: the ignore hid CVE-2026-4539 after the lock moved past the fix."""
    assert not [line for line in _audit_commands() if "CVE-2026-4539" in line]


def test_pip_audit_command_carries_no_ignore_flags() -> None:
    commands = _audit_commands()

    assert "pip-audit" in commands
    assert not [line for line in commands if "--ignore-vuln" in line]


def test_locked_pygments_is_past_the_cve_fix() -> None:
    """Positive premise: dropping the ignore is safe only while the lock holds the fix."""
    assert _locked_version("pygments") >= PYGMENTS_FIXED_IN
