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


@pytest.mark.parametrize("relative", FLOOR_SCRIPTS, ids=lambda path: path.as_posix())
def test_push_pr_scripts_avoid_post_310_datetime_alias(relative: Path) -> None:
    """Static guard that runs even where no 3.10 interpreter is installed.

    The runtime tests above skip on a host without CPython 3.10, and a skipped
    test protects nothing. This one always runs and pins the specific regression
    that shipped: ``datetime.UTC`` is 3.11+, while ``timezone.utc`` is available
    at every version this repository targets.
    """
    source = (REPO_ROOT / relative).read_text(encoding="utf-8")

    assert "from datetime import UTC" not in source, (
        f"{relative.as_posix()} imports datetime.UTC, which is Python 3.11+; "
        "use timezone.utc for the 3.10 hook-portability floor"
    )
    assert "datetime.UTC" not in source, (
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
