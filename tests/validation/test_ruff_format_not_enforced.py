"""``ruff format`` is not this repository's enforced formatter (issue #5304).

``.claude/rules/python.md`` tells every agent not to run ``ruff format`` and not
to cite ``ruff format --check`` as a gate result. That instruction is only
honest while two facts hold: no gate invokes the formatter, and the tree does
not conform to it. Both are measurable, and both can change without anybody
remembering the rule, so this module pins them.

Adopting the formatter is a legitimate future decision. This module is not a
veto on it; it is the tripwire that makes the rule text part of that decision
instead of a stale paragraph left behind by it.

- pos: no enforcement surface invokes ``ruff format``
- neg: the scanner does flag a surface that invokes it, and does flag the
       subprocess list form, proving the positive assertion has teeth
- edge: a commented-out or prose mention of ``ruff format`` is not an invocation
- guard: the tree is still materially non-conforming, and the rule text still
         carries the instruction these assertions back
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_RULE = REPO_ROOT / ".claude" / "rules" / "python.md"

# Every surface that can make a check blocking for a contributor: the local hook
# scheduler, CI, and the two validation runners CI and pre-push both call. A
# `ruff format` invocation anywhere in here is an enforcement, whatever its
# exit-code handling, because it puts the formatter on the path to a red gate.
_ENFORCEMENT_GLOBS = (
    "lefthook.yml",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "scripts/ci/*.py",
    "scripts/validation/pre_pr.py",
    "scripts/validation/pre_pr_sequence.py",
    "scripts/validation/git_hook_policy.py",
)

# Shell form (`ruff format`, including `uv run ... ruff format`) and the
# subprocess list form (`["ruff", "format", ...]`) that a Python runner uses.
_SHELL_INVOCATION = re.compile(r"\bruff\s+format\b")
_LIST_INVOCATION = re.compile(r"""(['"])ruff\1\s*,\s*(['"])format\2""")


def _strip_comment_lines(text: str) -> str:
    """Drop whole-line comments, the only place these files discuss tooling.

    Deliberately conservative: it removes lines whose first non-space character
    is ``#`` and nothing else. A trailing-comment stripper would need to know
    about quoting in both YAML and Python, and guessing wrong there would hide a
    real invocation, which is the one failure this module must not have.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _invocations(text: str) -> list[str]:
    """Return the ``ruff format`` invocations in ``text``, comments excluded."""
    body = _strip_comment_lines(text)
    return [
        line
        for line in body.splitlines()
        if _SHELL_INVOCATION.search(line) or _LIST_INVOCATION.search(line)
    ]


def _enforcement_files() -> list[Path]:
    found = [path for glob in _ENFORCEMENT_GLOBS for path in sorted(REPO_ROOT.glob(glob))]
    assert found, f"no enforcement surface matched {_ENFORCEMENT_GLOBS}; globs are stale"
    return found


def test_no_enforcement_surface_invokes_ruff_format() -> None:
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): lines
        for path in _enforcement_files()
        if (lines := _invocations(path.read_text(encoding="utf-8")))
    }

    assert not offenders, (
        "`ruff format` now runs in an enforcement surface, so the Tooling "
        "section of .claude/rules/python.md ('ruff format is not this repo's "
        "formatter. Do not run it.') is false. Either revert the gate or "
        "reformat the tree and rewrite that rule, then update this test. "
        f"Found: {offenders}"
    )


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


def test_tree_is_still_materially_non_conforming_to_ruff_format() -> None:
    """The rule's second premise: the formatter disagrees with most of main.

    A green ``ruff format --check`` would mean the tree converged and the
    do-not-run instruction had lost its cost argument. The threshold is loose on
    purpose; the claim under test is "materially non-conforming", not a count.
    Issue #5304 measured 1287 of 2061 files on ``cdf688a``.
    """
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
    would_reformat = sum(
        1 for line in result.stdout.splitlines() if line.startswith("Would reformat:")
    )

    assert would_reformat > 100, (
        "the tree now nearly conforms to `ruff format` "
        f"({would_reformat} files would reformat). Adopting the formatter is "
        "now cheap, so revisit .claude/rules/python.md rather than leaving a "
        "do-not-run instruction whose premise has expired."
    )


def test_python_rule_still_carries_the_instruction_this_module_backs() -> None:
    """Keep the guard and the instruction it backs from drifting apart.

    Collapses whitespace first so re-wrapping the rule (which the instruction
    budget regularly forces) does not read as the instruction being removed.
    """
    text = " ".join(PYTHON_RULE.read_text(encoding="utf-8").split())

    assert "Never run `ruff format`" in text
    assert "cite `ruff format --check` as a gate" in text
    assert Path(__file__).name in text, (
        "python.md should point at this module so a reader who changes the rule "
        "finds the guard that pins it"
    )
