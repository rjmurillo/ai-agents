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

import os
import shutil
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


def _scope_checked_text(text: str, diff_files: list[str]) -> str:
    formatter = getattr(mod, "format_scope_checked_text", None)
    assert formatter is not None, "format_scope_checked_text is missing"
    return formatter(text, diff_files)


def _run_git(args: list[str], cwd: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Scope Test",
        "GIT_AUTHOR_EMAIL": "scope-test@example.com",
        "GIT_COMMITTER_NAME": "Scope Test",
        "GIT_COMMITTER_EMAIL": "scope-test@example.com",
    }
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed in {cwd}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _create_two_worktrees() -> tuple[Path, Path, Path]:
    workspace = Path(PROJECT_ROOT) / ".pytest_tmp" / f"review-scope-{os.getpid()}"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    remote = workspace / "remote.git"
    main_repo = workspace / "main"
    requested = workspace / "requested"
    other = workspace / "other"

    _run_git(["init", "--bare", str(remote)], workspace)
    _run_git(["init", "-b", "main", str(main_repo)], workspace)
    (main_repo / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(["add", "README.md"], main_repo)
    _run_git(["commit", "-m", "initial"], main_repo)
    _run_git(["remote", "add", "origin", str(remote)], main_repo)
    _run_git(["push", "-u", "origin", "main"], main_repo)
    _run_git(["worktree", "add", "-b", "requested-branch", str(requested)], main_repo)
    _run_git(["worktree", "add", "-b", "other-branch", str(other)], main_repo)

    (requested / "requested.py").write_text("print('requested')\n", encoding="utf-8")
    _run_git(["add", "requested.py"], requested)
    _run_git(["commit", "-m", "requested change"], requested)

    (other / "other.py").write_text("print('other')\n", encoding="utf-8")
    _run_git(["add", "other.py"], other)
    _run_git(["commit", "-m", "other change"], other)
    return workspace, requested, other


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

    def test_bold_location_field_extracts_extensionless_path(self) -> None:
        text = "- **location**: `scripts/review-tool:47`\n"
        result = extract_locations(text)
        assert result == ["scripts/review-tool"]

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

    def test_free_form_file_path_is_extracted(self) -> None:
        text = "The classifier reported tests/test_doc_interpreter.py outside the bundle.\n"
        assert extract_locations(text) == ["tests/test_doc_interpreter.py"]


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


class TestScopeAdjustedText:
    def test_in_scope_critical_verdict_stays_critical(self) -> None:
        text = (
            "VERDICT: CRITICAL_FAIL\n"
            "- severity: CRITICAL\n"
            "  location: scripts/foo.py:10\n"
            "  recommendation: fix it\n"
        )

        adjusted = _scope_checked_text(text, ["scripts/foo.py"])

        assert "VERDICT: CRITICAL_FAIL" in adjusted
        assert "[pre-existing - not in this PR diff]" not in adjusted

    def test_out_of_scope_critical_verdict_downgrades_to_warn(self) -> None:
        text = (
            "VERDICT: CRITICAL_FAIL\n"
            "- severity: CRITICAL\n"
            "  location: scripts/unrelated.py:5\n"
            "  recommendation: fix it elsewhere\n"
        )

        adjusted = _scope_checked_text(text, ["scripts/foo.py"])

        assert "VERDICT: WARN" in adjusted
        assert "[pre-existing - not in this PR diff]" in adjusted
        assert "scripts/unrelated.py" in adjusted

    def test_no_locations_preserves_pass_verdict(self) -> None:
        text = "VERDICT: PASS\nNo findings.\n"

        adjusted = _scope_checked_text(text, ["scripts/foo.py"])

        assert adjusted == text

    def test_free_form_out_of_scope_path_downgrades_blocking_verdict(self) -> None:
        text = (
            "VERDICT: CRITICAL_FAIL\n"
            "The classifier reported tests/test_doc_interpreter.py, but the "
            "requested PR diff does not include it.\n"
        )

        adjusted = _scope_checked_text(text, ["scripts/foo.py"])

        assert "VERDICT: WARN" in adjusted
        assert "[pre-existing - not in this PR diff]" in adjusted

    def test_two_real_worktrees_use_requested_worktree_diff(self) -> None:
        workspace, requested, _other = _create_two_worktrees()
        try:
            diff_files = mod.get_diff_files(str(requested), "main")
            assert diff_files == ["requested.py"]
            text = (
                "VERDICT: CRITICAL_FAIL\n"
                "- severity: CRITICAL\n"
                "  location: other.py:1\n"
                "  recommendation: unrelated branch finding\n"
            )

            adjusted = _scope_checked_text(text, diff_files or [])

            assert "VERDICT: WARN" in adjusted
            assert "[pre-existing - not in this PR diff]" in adjusted
            assert "other.py" in adjusted
        finally:
            shutil.rmtree(workspace)


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
            text=True, encoding="utf-8",
        )
        # git diff will fail for a nonexistent branch -> graceful degrade -> exit 0
        assert result.returncode == 0

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True, encoding="utf-8",
        )
        assert result.returncode == 0
        assert "validate" in result.stdout.lower() or "worktree" in result.stdout.lower()
