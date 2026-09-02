"""Interpreter-floor regression tests for the push-pr scripts (issue #4764).

The repository develops on Python 3.14, but plugin hooks and skill scripts run
under the host's ambient interpreter. ``.claude/rules/python.md`` states the
floor:

    "plugin hooks and skill scripts run under the host's ambient interpreter,
    which may be older, so a blocking gate
    (scripts/validation/validate_python_syntax.py, issue #2655) requires every
    tracked file to parse at the hook-portability syntax floor, currently 3.10."

That gate parses. It cannot see a name that only exists in a newer standard
library, so a script can satisfy it and still fail at import on 3.10. This
module closes that gap for the push-pr bundle by executing the real scripts
under a real 3.10 interpreter.

Measured on the merged tree at ``5cd72a7dad`` with CPython 3.10.20:

    $ python3.10 .claude/skills/github/scripts/pr/new_pr.py --help
    Traceback (most recent call last):
      File ".../new_pr.py", line 21, in <module>
        from datetime import UTC, datetime
    ImportError: cannot import name 'UTC' from 'datetime'

``datetime.UTC`` is an alias for ``datetime.timezone.utc`` added in Python
3.11, so every 3.10 host lost ``/push-pr`` entirely at import time.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Scripts the push-pr flow executes on the host interpreter. Each must import
# and answer --help under the 3.10 floor.
FLOOR_SCRIPTS = (
    Path(".claude/skills/github/scripts/pr/new_pr.py"),
    Path(".claude/skills/github/scripts/pr/validate_pr_description.py"),
    Path("src/copilot-cli/skills/github/scripts/pr/new_pr.py"),
    Path("src/copilot-cli/skills/github/scripts/pr/validate_pr_description.py"),
)

# Bundle members that are libraries, not CLIs. They have no --help, so they are
# checked by executing the module body, which is what actually fails on a
# missing stdlib name.
FLOOR_MODULES = (
    Path(".claude/skills/github/scripts/pr/pr_validations.py"),
    Path("src/copilot-cli/skills/github/scripts/pr/pr_validations.py"),
)

# Host-executed scripts that get the static guard but not the runtime one,
# because something they import already breaks at 3.10 for a reason outside
# this module's scope.
#
# `test_pr_merge_ready.py` is invoked with a bare `python3` by both
# `.claude/commands/pr-review-config.yaml` and `.claude/commands/pr-autofix.md`,
# so it runs on the host interpreter exactly as `new_pr.py` does, and a draft
# of PR #5481 shipped `from datetime import UTC` into it. The syntax gate
# parsed that clean, because the name is 3.11+ stdlib rather than 3.11+ syntax,
# which is the gap this module exists to close, so the static guard below is
# what would have caught it.
#
# It cannot join FLOOR_SCRIPTS yet. Measured with CPython 3.10.20 against this
# tree: it imports `github_core.api`, which imports `github_core.review_threads`,
# whose `FetchStatus` subclasses `enum.StrEnum`, added in 3.11:
#
#     AttributeError: module 'enum' has no attribute 'StrEnum'
#
# That predates PR #5481 and belongs to the shared library rather than to any
# one script; `new_pr.py` passes the runtime test only because it imports no
# `github_core` module at all. Move these two entries into FLOOR_SCRIPTS once
# `FetchStatus` is spelled for the floor.
FLOOR_STATIC_ONLY = (
    Path(".claude/skills/github/scripts/pr/test_pr_merge_ready.py"),
    Path("src/copilot-cli/skills/github/scripts/pr/test_pr_merge_ready.py"),
)

ALL_FLOOR_FILES = FLOOR_SCRIPTS + FLOOR_MODULES + FLOOR_STATIC_ONLY


def _discover_python310() -> str | None:
    """Return a CPython 3.10 executable, or None when the host has none.

    Checked in cost order: an explicit override, then PATH, then the uv-managed
    interpreter directory that this repository's toolchain populates. Resolved
    at import time so ``pytest.mark.skipif`` can see it; a check inside a test
    body would be evaluated after collection and could not skip.
    """
    override = os.environ.get("PYTHON310")
    if override and Path(override).is_file():
        return override
    found = shutil.which("python3.10")
    if found:
        return found
    uv_root = Path.home() / ".local" / "share" / "uv" / "python"
    if uv_root.is_dir():
        candidates = sorted(uv_root.glob("cpython-3.10*/bin/python3.10"))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


PYTHON310 = _discover_python310()
requires_python310 = pytest.mark.skipif(
    PYTHON310 is None,
    reason=(
        "no CPython 3.10 available; set PYTHON310 to an interpreter path to run "
        "the hook-portability floor check (issue #4764)"
    ),
)


@requires_python310
@pytest.mark.parametrize("relative", FLOOR_SCRIPTS, ids=lambda path: path.as_posix())
def test_push_pr_scripts_import_on_python310(relative: Path) -> None:
    """The script must import and answer --help under the 3.10 floor.

    ``--help`` is the cheapest entry point that proves every module-level
    import executed: argparse only reaches the help text after the module body
    has run to completion. A test that merely compiled the file would pass with
    the ``from datetime import UTC`` defect present, because that line is
    syntactically valid on 3.10 and fails only when executed.
    """
    assert PYTHON310 is not None
    script = REPO_ROOT / relative

    result = subprocess.run(
        [PYTHON310, "-I", str(script), "--help"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0, (
        f"{relative.as_posix()} failed on {PYTHON310}: {result.stderr.strip()}"
    )
    assert "Traceback" not in result.stderr


@requires_python310
@pytest.mark.parametrize("relative", FLOOR_MODULES, ids=lambda path: path.as_posix())
def test_push_pr_modules_execute_on_python310(relative: Path) -> None:
    """A bundle library must execute its module body under the 3.10 floor.

    ``pr_validations.py`` has no CLI, so ``--help`` proves nothing about it.
    Executing the file is the equivalent check: every module-level import and
    every module-level statement runs, which is exactly where the
    ``from datetime import UTC`` class of defect fires.
    """
    assert PYTHON310 is not None
    script = REPO_ROOT / relative

    result = subprocess.run(
        [PYTHON310, "-I", str(script)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0, (
        f"{relative.as_posix()} failed on {PYTHON310}: {result.stderr.strip()}"
    )
    assert "Traceback" not in result.stderr


@requires_python310
def test_python310_is_actually_python310() -> None:
    """Negative control for the discovery helper.

    Without this, a discovery bug that returned the 3.14 interpreter would make
    every test above pass while measuring nothing. The failure it guards is the
    one that reads as a clean sweep.
    """
    assert PYTHON310 is not None
    result = subprocess.run(
        [PYTHON310, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "3.10", (
        f"discovery returned {result.stdout.strip()}, not a 3.10 interpreter"
    )


@pytest.mark.parametrize("relative", ALL_FLOOR_FILES, ids=lambda path: path.as_posix())
def test_push_pr_scripts_avoid_post_310_datetime_alias(relative: Path) -> None:
    """Static guard that runs even where no 3.10 interpreter is installed.

    The runtime tests above skip on a host without CPython 3.10, and a skipped
    test protects nothing. This one always runs and pins the specific regression
    that shipped: ``datetime.UTC`` is 3.11+, while ``timezone.utc`` is available
    at every version this repository targets.

    Asserts on the parsed syntax tree rather than on a substring of the source,
    per ``.claude/rules/testing.md`` MUST 9. A substring check reports a hit
    inside the comment that explains the fix, so it would fail on the fixed file
    and could only be satisfied by deleting the explanation.
    """
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            imported = {alias.name for alias in node.names}
            assert "UTC" not in imported, (
                f"{relative.as_posix()} imports datetime.UTC, which is Python 3.11+; "
                "use timezone.utc for the 3.10 hook-portability floor"
            )
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "UTC"
            and isinstance(node.value, ast.Name)
            and node.value.id == "datetime"
        ):
            raise AssertionError(
                f"{relative.as_posix()} references datetime.UTC, which is Python 3.11+"
            )


def test_repository_development_floor_is_unchanged() -> None:
    """The 3.10 fix must not lower the repository's own 3.14 development floor.

    ``.claude/rules/python.md`` ties the dev target to ``requires-python`` in
    pyproject.toml. Scripts written down to 3.10 are a hook-portability
    concession for the host interpreter, not a change of the project floor.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.14"' in pyproject, (
        "the repository development floor moved; the push-pr scripts target 3.10 "
        "only because plugin hosts supply the interpreter"
    )
    assert sys.version_info >= (3, 10)
