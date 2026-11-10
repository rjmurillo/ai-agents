"""The Python Security Checks job runs the ruff security rules even when pip-audit fails.

Issue #6028: pip-audit failed on a transitive pyjwt pin, and the default
success() condition then skipped the scan on every pull request. Bandit was later
replaced by ruff's equivalent rules. Assertions parse
the YAML object graph (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
UV_LOCK = REPO_ROOT / "uv.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"
SECURITY_STEP = "Run ruff security rules"

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


def _security_command() -> str:
    _, step = _step(SECURITY_STEP)
    return " ".join(str(step["run"]).replace("\\\n", " ").split())


def _step_select_codes() -> set[str]:
    match = re.search(r"--select (\S+)", _security_command())
    assert match is not None, "ruff security step passes no --select"
    return set(match.group(1).split(","))


def _pyproject_select_codes() -> set[str]:
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return set(document["tool"]["ruff"]["lint"]["select"])


def test_ruff_security_rules_run_after_pip_audit() -> None:
    audit_at, _ = _step("Run pip-audit")
    security_at, _ = _step(SECURITY_STEP)

    assert audit_at < security_at


def test_ruff_security_rules_do_not_depend_on_the_pip_audit_outcome() -> None:
    _, security = _step(SECURITY_STEP)

    assert security.get("if") == "${{ !cancelled() }}"


def test_bandit_is_gone_from_the_security_job() -> None:
    """Negative: no step may still install, run, or upload bandit output."""
    assert "bandit" not in str(_steps()).lower()


def test_step_select_is_a_subset_of_the_pyproject_select() -> None:
    """The workflow list cannot drift from the codes the main ruff gate enforces."""
    missing = _step_select_codes() - _pyproject_select_codes()

    assert not missing, f"codes in the workflow but not in pyproject select: {sorted(missing)}"


def test_every_pyproject_security_code_is_scanned_by_the_step() -> None:
    """Inverse: a security code added to pyproject must also reach the SARIF step."""
    in_pyproject = {c for c in _pyproject_select_codes() if re.fullmatch(r"S\d{3}|PLE\d{4}", c)}
    assert in_pyproject == _step_select_codes()


def test_pyproject_select_names_security_codes_one_by_one() -> None:
    """A prefix such as "S" or "S6" would bypass the exact-code drift checks above."""
    prefixes = {c for c in _pyproject_select_codes() if re.fullmatch(r"S\d{0,2}|PLE\d{0,3}", c)}

    assert not prefixes, f"prefix selectors in pyproject select: {sorted(prefixes)}"


# Each waiver is reviewed: the CodeQL installer must chmod its skill script
# 0o755, and tests were outside the retired bandit gate. The inline-suppression
# push gate does not read pyproject, so this test is what reviews a new waiver.
_ALLOWED_SECURITY_WAIVERS = {
    ".codeql/scripts/install_codeql_integration.py": {"S103"},
    "tests/**/*.py": {"S324", "S605"},
    "**/tests/**/*.py": {"S324", "S605"},
}


def test_security_codes_are_waived_only_where_reviewed() -> None:
    """A per-file-ignores entry silences the CI security step, so new ones must be listed."""
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    ignores = document["tool"]["ruff"]["lint"]["per-file-ignores"]
    waived = {
        glob: {c for c in codes if c.startswith(("S", "PLE"))} for glob, codes in ignores.items()
    }
    unreviewed = {
        glob: sorted(codes - _ALLOWED_SECURITY_WAIVERS.get(glob, set()))
        for glob, codes in waived.items()
        if codes - _ALLOWED_SECURITY_WAIVERS.get(glob, set())
    }

    assert not unreviewed, f"unreviewed security waivers in per-file-ignores: {unreviewed}"


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
