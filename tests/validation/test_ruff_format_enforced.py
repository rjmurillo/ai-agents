"""``ruff format`` is this repository's enforced formatter (issue #5304).

``.claude/rules/python.md`` tells every agent to run ``ruff format`` and to treat
``ruff format --check`` as a blocking gate. That instruction is only honest
while two facts hold: the gates invoke the formatter, and the tree conforms to
it. Both are measurable, so this module pins them.

- pos: CI and the local hook scheduler both invoke ``ruff format``
- neg: the scanner does flag a surface that invokes it, and does flag the
       subprocess list form, proving the positive assertion has teeth
- edge: a commented-out or prose mention of ``ruff format`` is not an invocation
- guard: the tree conforms, and the rule text still carries the instruction
         these assertions back
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_RULE = REPO_ROOT / ".claude" / "rules" / "python.md"

# Shell form (`ruff format`, including `uv run ... ruff format`) and the
# subprocess list form (`["ruff", "format", ...]`) that a Python runner uses.
_SHELL_INVOCATION = re.compile(r"\bruff\s+format\b")
_LIST_INVOCATION = re.compile(r"""(['"])ruff\1\s*,\s*(['"])format\2""")

# The summary line `ruff format --check` prints, e.g. "1637 files would be
# reformatted, 1472 files already formatted". ruff 0.16 replaced the per-file
# "Would reformat: <path>" lines with diagnostic blocks, so counting those lines
# read 0 on a tree with 1808 unformatted files. The summary line is the same on
# 0.15 and 0.16, so count from it instead.
_WOULD_REFORMAT_SUMMARY = re.compile(r"^(\d+) files? would be reformatted\b", re.MULTILINE)


def _would_reformat_count(returncode: int, stdout: str) -> int:
    """Return how many files ``ruff format --check`` would reformat.

    Exit 0 means every file is formatted. Exit 1 must carry the summary line;
    an unreadable summary fails instead of reading as 0, because 0 is the one
    value that would wrongly declare the tree conforming.
    """
    if returncode == 0:
        return 0
    match = _WOULD_REFORMAT_SUMMARY.search(stdout)
    assert match, (
        f"`ruff format --check` exited {returncode} without a "
        f"'N files would be reformatted' summary; output tail: {stdout[-500:]!r}"
    )
    return int(match.group(1))


def _strip_comment_lines(text: str) -> str:
    """Drop whole-line comments, the only place these files discuss tooling.

    Deliberately conservative: it removes lines whose first non-space character
    is ``#`` and nothing else. A trailing-comment stripper would need to know
    about quoting in both YAML and Python, and guessing wrong there would hide a
    real invocation, which is the one failure this module must not have.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _invocations(text: str) -> list[str]:
    """Return the ``ruff format`` invocations in ``text``, comments excluded."""
    body = _strip_comment_lines(text)
    return [
        line
        for line in body.splitlines()
        if _SHELL_INVOCATION.search(line) or _LIST_INVOCATION.search(line)
    ]


_REQUIRED_SURFACES = (".github/workflows/pytest.yml", "lefthook.yml")


@pytest.mark.parametrize("surface", _REQUIRED_SURFACES)
def test_required_enforcement_surface_invokes_ruff_format(surface: str) -> None:
    text = (REPO_ROOT / surface).read_text(encoding="utf-8")

    assert _invocations(text), (
        f"{surface} no longer invokes `ruff format`, so the Tooling section of "
        ".claude/rules/python.md ('Run the locked `ruff format` command; "
        "`ruff format --check` is a blocking gate.') is false. Restore the gate "
        "or rewrite that rule."
    )


def test_ci_format_step_is_blocking() -> None:
    """The CI step must not be advisory: no `continue-on-error` inside its block."""
    text = (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
    steps = re.split(r"(?m)^      - ", text)
    format_steps = [step for step in steps if _invocations(step)]

    assert format_steps, "pytest.yml has no step that invokes `ruff format`"
    assert all("continue-on-error" not in step for step in format_steps)


def test_force_exclude_keeps_staged_excludes_out_of_the_hook() -> None:
    """The lefthook hook passes explicit paths; ruff skips excludes for those unless forced."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert re.search(r"(?m)^force-exclude\s*=\s*true\s*$", pyproject)


def test_scanner_flags_a_shell_invocation_negative_control() -> None:
    surface = "      - name: format\n        run: uv run --frozen ruff format --check .\n"

    assert _invocations(surface) == ["        run: uv run --frozen ruff format --check ."]


def test_scanner_flags_a_subprocess_list_invocation_negative_control() -> None:
    surface = '    subprocess.run(["ruff", "format", "--check", *files], check=False)\n'

    assert len(_invocations(surface)) == 1


def test_scanner_ignores_a_commented_mention() -> None:
    surface = "# Do not add a `ruff format` job here; see issue #5304.\n  # ruff format .\n"

    assert _invocations(surface) == []


def test_scanner_ignores_ruff_check() -> None:
    surface = "        run: uv run --frozen --extra dev ruff check --fix --exit-zero\n"

    assert _invocations(surface) == []


def test_count_reads_the_ruff_0_15_summary() -> None:
    stdout = (
        "Would reformat: a.py\nWould reformat: b.py\n"
        "1637 files would be reformatted, 1472 files already formatted\n"
    )

    assert _would_reformat_count(1, stdout) == 1637


def test_count_reads_the_ruff_0_16_summary() -> None:
    stdout = (
        "unformatted: File would be reformatted\n"
        "    --> a.py:1:1\n"
        "1808 files would be reformatted, 6387 files already formatted\n"
    )

    assert _would_reformat_count(1, stdout) == 1808


def test_count_reads_the_singular_summary() -> None:
    assert _would_reformat_count(1, "1 file would be reformatted, 9 files already formatted\n") == 1


def test_count_is_zero_when_ruff_exits_clean() -> None:
    assert _would_reformat_count(0, "42 files already formatted\n") == 0


def test_count_fails_when_the_summary_is_missing() -> None:
    with pytest.raises(AssertionError, match="without a 'N files would be reformatted' summary"):
        _would_reformat_count(2, "error: Failed to parse pyproject.toml\n")


def test_tree_conforms_to_ruff_format() -> None:
    """The rule's second premise: the formatter agrees with the whole tree."""
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not on PATH; run under the uv dev environment")

    result = subprocess.run(
        ["ruff", "format", "--check", "."],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        check=False,
    )

    assert _would_reformat_count(result.returncode, result.stdout) == 0, (
        "`ruff format --check .` reports unformatted files; run `ruff format .`"
    )


def test_python_rule_still_carries_the_instruction_this_module_backs() -> None:
    """Keep the guard and the instruction it backs from drifting apart.

    Collapses whitespace first so re-wrapping the rule (which the instruction
    budget regularly forces) does not read as the instruction being removed.
    """
    text = " ".join(PYTHON_RULE.read_text(encoding="utf-8").split())

    assert "`uv run --frozen --extra dev ruff format <files>`" in text
    assert "`ruff format --check` is a blocking gate" in text
    assert Path(__file__).name in text, (
        "python.md should point at this module so a reader who changes the rule "
        "finds the guard that pins it"
    )
