"""Live-repository regressions for the documented-interpreter guard.

Split out of test_check_doc_interpreter_portability.py, which held both the
checker's synthetic unit tests and these assertions against the real tree and
crossed the 500-line taste limit. Everything here reads the working repository
rather than a tmp_path fixture, which is the seam.
"""


from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.check_doc_interpreter_portability import (
    find_offenses,
    main,
    scan,
    third_party_imports,
    tracked_files,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# The two surviving scripts issue #3791 names, and the module each one needs.
# (A third, scripts/sync_adr_protocol.py, was deleted along with the session
# skill cluster and .agents/SESSION-PROTOCOL.md, the doc it synced into.)
# Every one is a declared project dependency, so `uv run python` resolves it
# and a bare system interpreter may not.
ISSUE_3791_SCRIPTS = {
    "build/generate_agents.py": "yaml",
    "build/scripts/build_all.py": "yaml",
}


# --- regression: the issue #3791 surface stays fixed ------------------------


@pytest.mark.parametrize("doc", ["CONTRIBUTING.md"])
def test_onboarding_docs_name_no_bare_interpreter_for_issue_3791_scripts(doc: str) -> None:
    """The contributor-onboarding docs must not tell a reader to run these bare.

    A fresh checkout has no system PyYAML, so a bare `python3` invocation of an
    ISSUE_3791_SCRIPTS entry dies with ModuleNotFoundError. CONTRIBUTING.md is
    a required pre-submit read, which is why this is a blocking regression
    test rather than prose.
    """
    tracked_py = set(tracked_files(REPO_ROOT, "*.py"))
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")

    flagged = [
        (number, script)
        for number, line in enumerate(text.splitlines(), 1)
        for script, _ in find_offenses(line, REPO_ROOT, tracked_py)
        if script in ISSUE_3791_SCRIPTS
    ]

    assert flagged == []


def test_issue_3791_scripts_still_need_a_project_environment() -> None:
    """If a script stops importing its third-party module, the guard entry is stale.

    This is the negative control for the test above: it fails if the premise
    (these scripts need more than the stdlib) ever stops holding, rather than
    letting the regression test pass vacuously.
    """
    tracked_py = set(tracked_files(REPO_ROOT, "*.py"))

    for script, module in ISSUE_3791_SCRIPTS.items():
        assert module in third_party_imports(script, REPO_ROOT, tracked_py), (
            f"{script} no longer imports {module}; revisit the issue #3791 doc fix"
        )


def test_repository_is_at_or_below_its_baseline() -> None:
    exit_code = main(["--repo-root", str(REPO_ROOT)])

    assert exit_code == 0


@pytest.mark.parametrize(
    "path",
    ["src/claude/AGENTS.md"],
)
def test_named_regression_files_carry_no_bare_interpreter(path: str) -> None:
    """Scan two specific files without consulting the guard's scope configuration.

    `test_repository_has_no_documented_bare_interpreter_invocations` routes
    through `scan`, which asks `is_in_scope` first. Putting a root back into
    `GENERATED_ROOTS` therefore silences it, which is exactly how
    `src/claude/AGENTS.md` stayed broken. This reads the bytes directly, so the
    only way to make it pass is to fix the file.
    """
    tracked_py = set(tracked_files(REPO_ROOT, "*.py"))
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    flagged = [
        f"{path}:{number} {script}"
        for number, line in enumerate(text.splitlines(), 1)
        for script, _ in find_offenses(line, REPO_ROOT, tracked_py)
    ]

    assert flagged == [], "bare interpreter came back: " + ", ".join(flagged)


def test_repository_has_no_documented_bare_interpreter_invocations() -> None:
    """No in-scope file may name a bare interpreter for a non-stdlib script.

    Issue #3791 named one instance (`scripts/sync_adr_protocol.py` in
    CONTRIBUTING.md). Fixing only that one left the identical shape across the
    Markdown tree, then across `src/claude/` and the Python usage docstrings and
    printed remediation strings, all of which die with the same
    ModuleNotFoundError on a clean checkout. The correct count is zero, and this
    asserts the whole class rather than the named instance.

    Stronger than `test_repository_is_at_or_below_its_baseline`, which a
    `--update-baseline` run would satisfy by grandfathering a new offender.
    """
    offenders = scan(REPO_ROOT)

    assert offenders == {}, (
        "documented bare-interpreter invocations came back: "
        + ", ".join(f"{rel} ({count})" for rel, count in sorted(offenders.items()))
        + ". Use 'uv run python <script>' (issue #3791)."
    )


def test_bare_python3_still_fails_for_a_declared_dependency() -> None:
    """Ground the whole guard in the real interpreter, not in our import model."""
    result = subprocess.run(
        [sys.executable, "-S", "-c", "import yaml"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        pytest.skip("this interpreter has system-wide PyYAML, so -S cannot isolate it")
    assert "ModuleNotFoundError" in result.stderr
