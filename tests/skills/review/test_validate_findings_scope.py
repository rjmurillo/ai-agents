"""Tests for the ``/review`` skill's findings-scope validator (issue #4020).

Locks the contract for ``validate_findings_scope.py``:
- ``extract_locations`` parses ``location: file:line`` from axis text.
- ``_looks_like_path`` rejects prose tokens and accepts file paths.
- ``validate_scope`` splits locations into in-scope and out-of-scope buckets.
- ``main`` exits 0 when all locations are in scope and 1 when any are not.
- ``main`` exits 0 (graceful degrade) when the diff cannot be obtained.

Each subsection includes a negative control: the test would fail if the
relevant function were stubbed to always return the "clean" value.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/validate_findings_scope.py",
    module_name="validate_findings_scope",
)

extract_locations = mod.extract_locations
validate_scope = mod.validate_scope
_looks_like_path = mod._looks_like_path
_strip_line_suffix = mod._strip_line_suffix
main = mod.main


# ---------------------------------------------------------------------------
# _looks_like_path
# ---------------------------------------------------------------------------


class TestLooksLikePath:
    def test_path_with_slash_is_path(self) -> None:
        assert _looks_like_path("scripts/foo.py") is True

    def test_path_with_known_extension_is_path(self) -> None:
        assert _looks_like_path("readme.md") is True

    def test_prose_token_not_a_path(self) -> None:
        assert _looks_like_path("N/A") is False

    def test_integer_not_a_path(self) -> None:
        assert _looks_like_path("42") is False

    def test_bare_word_not_a_path(self) -> None:
        assert _looks_like_path("line") is False

    # Negative control: if _looks_like_path always returned True, the prose
    # token test above would fail.
    def test_negative_control_prose_rejected(self) -> None:
        for token in ("line 42", "N/A", "global", "unknown"):
            assert not _looks_like_path(token), f"expected False for {token!r}"


# ---------------------------------------------------------------------------
# _strip_line_suffix
# ---------------------------------------------------------------------------


class TestStripLineSuffix:
    def test_strips_single_line(self) -> None:
        assert _strip_line_suffix("scripts/foo.py:42") == "scripts/foo.py"

    def test_strips_line_range(self) -> None:
        assert _strip_line_suffix("scripts/foo.py:42-55") == "scripts/foo.py"

    def test_no_suffix_unchanged(self) -> None:
        assert _strip_line_suffix("scripts/foo.py") == "scripts/foo.py"


# ---------------------------------------------------------------------------
# extract_locations
# ---------------------------------------------------------------------------


class TestExtractLocations:
    def test_single_location_field(self) -> None:
        text = "- **location**: `scripts/foo.py:10`\n"
        result = extract_locations(text)
        assert "scripts/foo.py" in result

    def test_case_insensitive_field_name(self) -> None:
        text = "Location: scripts/foo.py:5\n"
        result = extract_locations(text)
        assert "scripts/foo.py" in result

    def test_multiple_locations(self) -> None:
        text = (
            "location: scripts/foo.py:10\n"
            "location: tests/test_bar.py:20\n"
        )
        result = extract_locations(text)
        assert "scripts/foo.py" in result
        assert "tests/test_bar.py" in result

    def test_prose_token_not_extracted(self) -> None:
        text = "location: N/A\n"
        result = extract_locations(text)
        assert result == []

    def test_backtick_wrapped_path(self) -> None:
        text = "- **location**: `src/auth/login.ts:47`\n"
        result = extract_locations(text)
        assert "src/auth/login.ts" in result

    # Negative control: if extract_locations returned every token, prose
    # tokens like "N/A" would appear in the output.
    def test_negative_control_prose_excluded(self) -> None:
        text = "location: N/A\nlocation: unknown\nlocation: line 42\n"
        result = extract_locations(text)
        assert not any(r in ("N/A", "unknown") for r in result)

    def test_empty_text_returns_empty(self) -> None:
        assert extract_locations("") == []

    def test_no_location_field_returns_empty(self) -> None:
        text = "This axis found no issues in the PR.\nVerdict: PASS\n"
        assert extract_locations(text) == []


# ---------------------------------------------------------------------------
# validate_scope
# ---------------------------------------------------------------------------


class TestValidateScope:
    def test_in_scope_location(self) -> None:
        text = "location: scripts/foo.py:10\n"
        in_scope, out_of_scope = validate_scope(text, ["scripts/foo.py"])
        assert "scripts/foo.py" in in_scope
        assert out_of_scope == []

    def test_out_of_scope_location(self) -> None:
        text = "location: scripts/unrelated.py:5\n"
        in_scope, out_of_scope = validate_scope(text, ["scripts/foo.py"])
        assert "scripts/unrelated.py" in out_of_scope
        assert in_scope == []

    def test_empty_diff_files_all_in_scope(self) -> None:
        """When diff is unavailable (empty list), degrade gracefully."""
        text = "location: scripts/unrelated.py:5\n"
        in_scope, out_of_scope = validate_scope(text, [])
        assert out_of_scope == []

    def test_suffix_match_passes(self) -> None:
        """A bare filename matches a path that ends with it."""
        text = "location: foo.py:1\n"
        in_scope, out_of_scope = validate_scope(text, ["src/foo.py"])
        assert "foo.py" in in_scope
        assert out_of_scope == []

    def test_mixed_in_and_out(self) -> None:
        text = (
            "location: scripts/foo.py:10\n"
            "location: scripts/unrelated.py:5\n"
        )
        in_scope, out_of_scope = validate_scope(text, ["scripts/foo.py"])
        assert "scripts/foo.py" in in_scope
        assert "scripts/unrelated.py" in out_of_scope

    # Negative control: if validate_scope always returned everything as
    # in-scope, out_of_scope would always be [] and the "out of scope" test
    # above would fail.
    def test_negative_control_oos_detected(self) -> None:
        text = "location: completely-unrelated.py:1\n"
        _, out_of_scope = validate_scope(text, ["scripts/foo.py", "tests/bar.py"])
        assert len(out_of_scope) > 0


# ---------------------------------------------------------------------------
# main (CLI entry point)
# ---------------------------------------------------------------------------


class TestMain:
    def test_all_in_scope_exits_zero(self) -> None:
        text = "location: scripts/foo.py:10\n"
        with patch.object(mod, "get_diff_files", return_value=["scripts/foo.py"]):
            rc = main(["--worktree", ".", "--base-branch", "main", "--text", text])
        assert rc == 0

    def test_out_of_scope_exits_one(self) -> None:
        text = "location: scripts/unrelated.py:5\n"
        with patch.object(mod, "get_diff_files", return_value=["scripts/foo.py"]):
            rc = main(["--worktree", ".", "--base-branch", "main", "--text", text])
        assert rc == 1

    def test_diff_unavailable_exits_zero(self) -> None:
        """Graceful degrade: when git fails, exit 0 to avoid blocking review."""
        text = "location: scripts/unrelated.py:5\n"
        with patch.object(mod, "get_diff_files", return_value=None):
            rc = main(["--worktree", ".", "--base-branch", "main", "--text", text])
        assert rc == 0

    def test_no_locations_exits_zero(self) -> None:
        text = "No findings. Verdict: PASS\n"
        with patch.object(mod, "get_diff_files", return_value=["scripts/foo.py"]):
            rc = main(["--worktree", ".", "--base-branch", "main", "--text", text])
        assert rc == 0

    # Negative control: if main always exited 0, the out-of-scope test above
    # would fail (it asserts rc == 1).
    def test_negative_control_oos_triggers_nonzero(self) -> None:
        text = "location: ghost-file-not-in-pr.py:99\n"
        with patch.object(mod, "get_diff_files", return_value=["real-file.py"]):
            rc = main(["--worktree", ".", "--base-branch", "main", "--text", text])
        assert rc != 0


# ---------------------------------------------------------------------------
# CLI subprocess test (validates exit-code contract end-to-end)
# ---------------------------------------------------------------------------


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "review"
    / "scripts"
    / "validate_findings_scope.py"
)


class TestCLISubprocess:
    """Exercise the script via subprocess to verify the exit-code contract."""

    def test_script_exists_and_is_executable(self) -> None:
        assert SCRIPT_PATH.is_file(), f"script not found: {SCRIPT_PATH}"

    def test_exit_0_on_empty_text(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--base-branch", "nonexistent-branch-xyz"],
            input="No findings. Verdict: PASS\n",
            capture_output=True,
            text=True,
        )
        # git diff will fail for a nonexistent branch -> graceful degrade -> exit 0
        assert result.returncode == 0

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "validate" in result.stdout.lower() or "worktree" in result.stdout.lower()
