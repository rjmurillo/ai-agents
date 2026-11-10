"""The ruff security codes stay in step between pyproject and the CI scan.

The main ruff gate reads ``[tool.ruff.lint] select``; the CI security step in
``pytest.yml`` passes its own ``--select`` so its SARIF holds only security
findings. These tests keep the two lists equal, keep every code named one by
one, and require review for any per-file waiver of a security code. They parse
TOML and YAML instead of matching text (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
SECURITY_STEP = "Run ruff security rules"


def _step(name: str) -> tuple[int, dict[str, Any]]:
    document = yaml.safe_load(PYTEST_WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["security"]["steps"]
    matches = [(i, step) for i, step in enumerate(steps) if step.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


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


def _security(codes: list[str]) -> set[str]:
    return {c for c in codes if c.startswith(("S", "PLE"))}


def _ruff_tables() -> list[dict[str, Any]]:
    """Ruff reads lint settings from [tool.ruff.lint] and, deprecated, from [tool.ruff]."""
    ruff = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["ruff"]
    return [ruff, ruff.get("lint", {})]


def test_security_codes_are_waived_only_where_reviewed() -> None:
    """Both per-file tables silence the CI security step, so a new waiver must be listed."""
    waived: dict[str, set[str]] = {}
    for table in _ruff_tables():
        for key in ("per-file-ignores", "extend-per-file-ignores"):
            for glob, codes in table.get(key, {}).items():
                waived.setdefault(glob, set()).update(_security(codes))
    unreviewed = {
        glob: sorted(codes - _ALLOWED_SECURITY_WAIVERS.get(glob, set()))
        for glob, codes in waived.items()
        if codes - _ALLOWED_SECURITY_WAIVERS.get(glob, set())
    }

    assert not unreviewed, f"unreviewed per-file security waivers: {unreviewed}"


def test_security_codes_are_never_ignored_repo_wide() -> None:
    """An S or PLE code in ignore or extend-ignore turns the check off everywhere."""
    ignored = {
        code
        for table in _ruff_tables()
        for key in ("ignore", "extend-ignore")
        for code in _security(table.get(key, []))
    }

    assert not ignored, f"security codes ignored repo-wide: {sorted(ignored)}"
