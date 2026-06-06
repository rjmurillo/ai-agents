"""Regression tests for #2442: pre-commit grep-count fallback produces "0\\n0".

`.githooks/pre-commit` counted upstream-filtered staged files using the idiom
`grep -c . || echo 0`. When the input is empty, `grep -c .` prints `0` and
exits 1, then `|| echo 0` appends a second `0`. Command substitution then
yields `"0\\n0"`, which fails `$(( ))` arithmetic with
`syntax error in expression (error token is "0")`. The commit still succeeds
because the failed arithmetic happens inside an unchecked branch, but the
hook emits a scary shell error that wastes agent time on diagnosis.

The fix is to route both counts through a `count_nonempty_lines` helper that
takes a string and prints exactly one integer, no matter how many lines the
input has (including zero).

These tests:

1. Prove the buggy idiom `grep -c . || echo 0` emits the multi-line garbage
   and a subsequent `$(( ))` blows up on it (negative control).
2. Prove the new `count_nonempty_lines` helper emits a single integer for
   the empty, single-line, and multi-line cases, and that arithmetic on its
   output succeeds.
3. Pin the committed hook so the buggy idiom cannot be reintroduced and the
   helper is actually used at the two known call sites.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"


def _run_bash(snippet: str) -> subprocess.CompletedProcess[str]:
    """Run a bash snippet with `set -e` (matching the hook's shell options)."""
    wrapped = "set -e\n" + snippet
    return subprocess.run(
        ["bash", "-c", wrapped],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=10,
    )


# The buggy idiom the fix replaces. Kept as a negative control so the bug
# stays demonstrable and any future "is this really broken?" debate ends here.
_BUGGY_COUNT = 'COUNT=$(echo "$INPUT" | grep -c . || echo 0)\nprintf "%s" "$COUNT"\n'

# The fix: a helper that normalizes to a single integer for any input shape.
# This is the same shape committed to .githooks/pre-commit (see hook for the
# canonical definition; this is a copy for unit-level coverage that does not
# depend on the rest of the hook running).
_HELPER = """
count_nonempty_lines() {
    # Print the number of non-empty lines in $1 on stdout, as a single
    # integer with no trailing whitespace. Always exits 0; never emits more
    # than one line. Empty input prints 0.
    local input="$1"
    if [ -z "$input" ]; then
        printf '0'
        return 0
    fi
    # awk's final printf returns one normalized integer for the hook's
    # arithmetic, regardless of whether any non-empty lines were seen.
    printf '%s' "$input" | awk 'NF{c++} END{printf "%d", c+0}'
}
"""


class TestBuggyIdiomReproducesIssue:
    """Negative control: prove the documented bug exists with the old shape."""

    def test_buggy_count_yields_multiline_garbage_on_empty(self) -> None:
        result = _run_bash('INPUT=""\n' + _BUGGY_COUNT)
        assert result.returncode == 0, result.stderr
        # The whole point of the bug: COUNT is "0\n0", not "0".
        assert result.stdout == "0\n0", (
            f"expected the buggy idiom to produce '0\\n0'; got {result.stdout!r}"
        )

    def test_buggy_count_breaks_arithmetic_on_empty(self) -> None:
        snippet = (
            'INPUT=""\n'
            'COUNT=$(echo "$INPUT" | grep -c . || echo 0)\n'
            "SKIPPED=$(( COUNT - 0 ))\n"
            'echo "SKIPPED=$SKIPPED"\n'
        )
        result = _run_bash(snippet)
        # Reproduces the exact symptom from #2442: bash prints "syntax error
        # in expression (error token is "0")" to stderr. The script as a
        # whole may still exit 0 because set -e doesn't always trip on
        # arithmetic failures at top level (which is exactly why this bug
        # has been shipping silently for so long: the commit succeeds but
        # the user sees the scary stderr message in the hook output).
        assert "syntax error in expression" in result.stderr, (
            f"expected bash to print arithmetic syntax error; stderr={result.stderr!r}"
        )
        assert 'error token is "0"' in result.stderr, result.stderr
        # And the variable ends up empty (a silent data-loss bug on top of
        # the noisy stderr error).
        assert result.stdout == "SKIPPED=\n", (
            f"expected SKIPPED to be empty after failed arithmetic; got {result.stdout!r}"
        )


class TestHelperHandlesAllShapes:
    """The fix: count_nonempty_lines emits exactly one integer."""

    def _count(self, input_value: str) -> str:
        snippet = (
            _HELPER + f"INPUT={_bash_quote(input_value)}\n" + 'count_nonempty_lines "$INPUT"\n'
        )
        result = _run_bash(snippet)
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_empty_input_is_zero(self) -> None:
        assert self._count("") == "0"

    def test_single_nonempty_line_is_one(self) -> None:
        assert self._count("foo") == "1"

    def test_single_line_with_trailing_newline_is_one(self) -> None:
        assert self._count("foo\n") == "1"

    def test_two_lines_is_two(self) -> None:
        assert self._count("foo\nbar") == "2"

    def test_blank_lines_are_excluded(self) -> None:
        # Empty lines (whitespace-only NF=0 in awk) must not be counted; the
        # callers want a count of files, and blank lines do not name files.
        assert self._count("foo\n\nbar\n") == "2"

    def test_whitespace_only_input_is_zero(self) -> None:
        assert self._count("\n\n\n") == "0"

    def test_arithmetic_on_helper_output_succeeds_on_empty(self) -> None:
        """The whole point of the fix: subtraction must work on empty input."""
        snippet = (
            _HELPER
            + 'ORIG=""\n'
            + 'FILT=""\n'
            + 'ORIGINAL_COUNT=$(count_nonempty_lines "$ORIG")\n'
            + 'FILTERED_COUNT=$(count_nonempty_lines "$FILT")\n'
            + "SKIPPED_COUNT=$(( ORIGINAL_COUNT - FILTERED_COUNT ))\n"
            + 'echo "SKIPPED=$SKIPPED_COUNT"\n'
        )
        result = _run_bash(snippet)
        assert result.returncode == 0, (
            f"arithmetic must succeed on helper output; stderr={result.stderr}"
        )
        assert result.stdout.strip() == "SKIPPED=0"

    def test_arithmetic_on_helper_output_succeeds_nonzero_difference(self) -> None:
        snippet = (
            _HELPER
            + r'ORIG=$(printf "a\nb\nc\n")'
            + "\n"
            + r'FILT=$(printf "a\n")'
            + "\n"
            + 'ORIGINAL_COUNT=$(count_nonempty_lines "$ORIG")\n'
            + 'FILTERED_COUNT=$(count_nonempty_lines "$FILT")\n'
            + "SKIPPED_COUNT=$(( ORIGINAL_COUNT - FILTERED_COUNT ))\n"
            + 'echo "SKIPPED=$SKIPPED_COUNT"\n'
        )
        result = _run_bash(snippet)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "SKIPPED=2"


class TestHookPinsFixedShape:
    """Pin the committed hook so the fix cannot be regressed."""

    def test_hook_defines_count_helper(self) -> None:
        text = PRE_COMMIT.read_text(encoding="utf-8")
        assert "count_nonempty_lines()" in text, (
            "expected hook to define a count_nonempty_lines() helper"
        )

    def test_hook_does_not_use_buggy_grep_c_echo_zero(self) -> None:
        """The old `grep -c . || echo 0` shape must not appear in non-comment lines."""
        text = PRE_COMMIT.read_text(encoding="utf-8")
        code_lines = [
            re.split(r"\s+#", line, maxsplit=1)[0]
            for line in text.splitlines()
            if not line.lstrip().startswith("#")
        ]
        offenders = [
            line for line in code_lines if re.search(r"grep\s+-c\s+\.\s*\|\|\s*echo\s+0", line)
        ]
        assert offenders == [], (
            f"buggy 'grep -c . || echo 0' idiom must not be reintroduced; offenders={offenders}"
        )

    def test_hook_uses_helper_for_both_counts(self) -> None:
        """ORIGINAL_COUNT and FILTERED_COUNT must both route through the helper."""
        text = PRE_COMMIT.read_text(encoding="utf-8")
        # Both assignments should use count_nonempty_lines; we accept any
        # whitespace between assignment and the helper call.
        assert re.search(
            r"ORIGINAL_COUNT=\$\(\s*count_nonempty_lines\s+",
            text,
        ), "ORIGINAL_COUNT must be computed via count_nonempty_lines"
        assert re.search(
            r"FILTERED_COUNT=\$\(\s*count_nonempty_lines\s+",
            text,
        ), "FILTERED_COUNT must be computed via count_nonempty_lines"


def _bash_quote(value: str) -> str:
    """Single-quote a string for safe inclusion in a bash assignment."""
    return "'" + value.replace("'", "'\\''") + "'"
