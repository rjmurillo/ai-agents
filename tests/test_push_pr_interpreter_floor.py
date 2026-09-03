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
import re
import shutil
import subprocess
import sys
from datetime import datetime
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
    # Promoted from FLOOR_STATIC_ONLY: the `enum.StrEnum` in
    # `github_core.review_threads` that blocked these is spelled for the floor
    # now, so the runtime guard applies (PR #5509).
    Path(".claude/skills/github/scripts/pr/test_pr_merge_ready.py"),
    Path("src/copilot-cli/skills/github/scripts/pr/test_pr_merge_ready.py"),
    # The transport preflight is host-executed with a bare `python3` from
    # Phase 0 of pr-autofix and Step 0 of pr-review, so a floor break here
    # takes the whole workflow before it can pick a transport.
    Path(".claude/skills/github/scripts/utils/check_github_transport.py"),
    Path("src/copilot-cli/skills/github/scripts/utils/check_github_transport.py"),
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
# `test_pr_merge_ready.py` used to sit here because it imports
# `github_core.api`, which imports `github_core.review_threads`, whose
# `FetchStatus` subclassed `enum.StrEnum` (3.11+) and raised
# `AttributeError: module 'enum' has no attribute 'StrEnum'` on 3.10. That
# note asked for the entries to move once `FetchStatus` was spelled for the
# floor. PR #5509 did that, along with the `datetime.UTC` aliases in
# `github_core.output` and `github_core.recovery_manifest`, so both entries are
# in FLOOR_SCRIPTS above and get the runtime guard.
#
# Nothing is static-only today. Keep the tuple rather than deleting it: it is
# the documented place for the next script whose import closure breaks at the
# floor for a reason outside its own file.
FLOOR_STATIC_ONLY: tuple[Path, ...] = ()

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


# ---------------------------------------------------------------------------
# Cross-version parity for the disposition expiry grammar (PR #5481)
# ---------------------------------------------------------------------------

_MERGE_READY = Path(".claude/skills/github/scripts/pr/test_pr_merge_ready.py")

# The values `_EXPIRES_PATTERN` is meant to accept. Every one must parse on the
# 3.10 floor as well as on the development interpreter, or the same registry
# yields different merge verdicts on different hosts.
_ACCEPTED_EXPIRIES = (
    "2999-01-01",
    "2999-01-01T12:30:00",
    "2999-01-01T12:30:00Z",
    "2999-01-01T12:30:00+00:00",
    "2999-01-01T12:30:00-08:00",
    "2999-01-01T12:30:00.123+00:00",
    "2999-01-01T12:30:00.123456+00:00",
    "2999-01-01 12:30:00+00:00",
)


def _expires_pattern_source() -> str:
    """The regex literal `_EXPIRES_PATTERN` compiles, read from the source.

    Read out of the AST rather than imported. The original reason was that the
    script could not be imported under 3.10 at all, because
    `github_core.review_threads` subclassed `enum.StrEnum` (3.11); that is
    fixed on this branch and the script now runs on the floor, which is why
    `test_pr_merge_ready.py` moved into FLOOR_SCRIPTS above.

    Extraction stays, for the reason that outlives the import fault: importing
    binds a compiled `re.Pattern` object, and `.pattern` on it round-trips
    through the regex engine rather than reporting the literal the file ships.
    Reading the literal keeps this measuring the shipped pattern rather than a
    copy that can drift away from it, and it keeps working if the closure
    reacquires a floor-breaking import later.
    """
    tree = ast.parse((REPO_ROOT / _MERGE_READY).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_EXPIRES_PATTERN" not in targets:
            continue
        call = node.value
        assert isinstance(call, ast.Call), "_EXPIRES_PATTERN must be a re.compile call"
        return ast.literal_eval(call.args[0])
    raise AssertionError("_EXPIRES_PATTERN not found in the readiness script")


def test_the_expiry_pattern_literal_is_readable() -> None:
    """Negative control for the extractor.

    The parity test below skips without a 3.10 interpreter, and a broken
    extractor would then fail loudly here instead of hiding behind that skip.
    """
    source = _expires_pattern_source()
    assert source.startswith(r"\d{4}-\d{2}-\d{2}"), source
    assert re.match(source, "2999-01-01"), source
    assert not re.match(source, "29990101"), source


@requires_python310
def test_accepted_expiries_parse_identically_on_the_floor() -> None:
    """Every value the grammar admits must parse on 3.10, not only on 3.14.

    `datetime.fromisoformat` is not one parser across these versions: 3.11
    widened it to most of ISO 8601. `_EXPIRES_PATTERN` exists to pin the
    subset both accept, and this is the half of that claim a single-version
    test cannot make. Without it, widening the pattern to a 3.11-only form
    would pass the whole suite on the development interpreter and silently
    treat a live disposition as expired on a plugin host.
    """
    assert PYTHON310 is not None
    pattern = _expires_pattern_source()
    probe = (
        "import re, sys\n"
        "from datetime import datetime\n"
        f"pattern = re.compile({pattern!r})\n"
        f"values = {list(_ACCEPTED_EXPIRIES)!r}\n"
        "for value in values:\n"
        "    assert pattern.match(value), 'pattern rejects ' + value\n"
        "    normalized = value[:-1] + '+00:00' if value.endswith('Z') else value\n"
        "    datetime.fromisoformat(normalized)\n"
        "print('ok')\n"
    )

    result = subprocess.run(
        [PYTHON310, "-c", probe],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@requires_python310
def test_rejected_expiries_are_the_ones_the_floor_cannot_parse() -> None:
    """The inverse: the forms the grammar refuses are refused for a reason.

    Each of these parses on the development interpreter and raises on 3.10,
    which is the divergence the pattern exists to remove. If a future CPython
    made them parse everywhere, this test fails and the pattern can widen on
    evidence rather than on assumption.
    """
    # Only the forms that genuinely disagree between the two versions.
    # `2999-01-01T12` and `2999-01-01T12:30` parse on 3.10 as well, so the
    # grammar excludes them for strictness rather than for portability and
    # they would fail the 3.10 half of this assertion.
    assert PYTHON310 is not None
    diverging = [
        "29990101",
        "2999-W01-1",
        "2999-01-01T12:30:00+0000",
        "2999-01-01T12:30:00.1+00:00",
        "2999-01-01T12:30:00.1234+00:00",
    ]
    pattern = re.compile(_expires_pattern_source())
    for value in diverging:
        assert not pattern.match(value), f"grammar admits {value}"
        datetime.fromisoformat(value)  # parses here, on the dev interpreter

    probe = (
        "from datetime import datetime\n"
        f"for value in {diverging!r}:\n"
        "    try:\n"
        "        datetime.fromisoformat(value)\n"
        "    except ValueError:\n"
        "        continue\n"
        "    raise SystemExit('3.10 now parses ' + value)\n"
        "print('ok')\n"
    )

    result = subprocess.run(
        [PYTHON310, "-c", probe],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
