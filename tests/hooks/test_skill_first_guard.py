"""Tests for PreToolUse invoke_skill_first_guard hook.

Verifies that raw gh commands are blocked when a validated skill script exists,
and allowed when no skill exists for the operation.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

from invoke_skill_first_guard import (  # noqa: E402
    SKILL_MAPPINGS,
    find_skill_script,
    main,
    parse_gh_command,
    write_block_response,
)


class TestParseGhCommand:
    """Tests for gh command parsing."""

    def test_pr_create(self) -> None:
        result = parse_gh_command("gh pr create --title test")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "create"

    def test_issue_list(self) -> None:
        result = parse_gh_command("gh issue list")
        assert result is not None
        assert result["operation"] == "issue"
        assert result["action"] == "list"

    def test_not_gh_command(self) -> None:
        assert parse_gh_command("git push origin main") is None

    def test_empty_string(self) -> None:
        assert parse_gh_command("") is None

    def test_whitespace_only(self) -> None:
        assert parse_gh_command("   ") is None

    def test_gh_with_pipe(self) -> None:
        result = parse_gh_command("gh pr view 123 | head")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"

    def test_gh_single_word(self) -> None:
        """gh with only operation and no action should not match."""
        assert parse_gh_command("gh auth") is None

    def test_preserves_full_command(self) -> None:
        cmd = "gh pr merge 123 --squash"
        result = parse_gh_command(cmd)
        assert result is not None
        assert result["full_command"] == cmd

    def test_gh_in_chain(self) -> None:
        result = parse_gh_command("cd repo && gh pr view 7")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"

    def test_quoted_gh_subcommand_not_flagged(self) -> None:
        """Issue #2111: a gh subcommand mentioned inside a quoted argument of a
        non-gh command must NOT be treated as a gh invocation."""
        assert parse_gh_command('python3 triage.py --title "gh issue list output"') is None
        assert parse_gh_command("echo 'run gh pr view to inspect'") is None
        assert parse_gh_command('grep -r "gh pr create" .') is None

    def test_env_prefixed_gh_still_parsed(self) -> None:
        """A real gh invocation behind an env assignment or sudo is still caught."""
        result = parse_gh_command("GH_TOKEN=xyz gh pr view 1")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"
        result2 = parse_gh_command("sudo gh issue list")
        assert result2 is not None
        assert result2["operation"] == "issue"
        assert result2["action"] == "list"

    def test_gh_substring_command_not_flagged(self) -> None:
        """A command whose name merely ends in 'gh' is not gh."""
        assert parse_gh_command("high pr view 1") is None
        assert parse_gh_command("/usr/bin/weigh pr list") is None

    def test_wrapper_prefixes_with_options_still_parsed(self) -> None:
        """gh behind transparent wrappers with their own option flags is caught.

        Regression for the skills-first bypass: sudo -E gh, env -i gh, nohup gh,
        and time gh must all resolve to the gh command word so the guard nudges.
        """
        for cmd in (
            "sudo -E gh pr view 1",
            "env -i gh issue list",
            "env FOO=bar gh pr view 1",
            "nohup gh pr view 1",
            "time gh issue list",
        ):
            result = parse_gh_command(cmd)
            assert result is not None, cmd

    def test_quoted_env_assignment_with_spaces_still_parsed(self) -> None:
        """A quoted env assignment that contains spaces must not misalign the
        command-word lookup; the following gh is still detected."""
        result = parse_gh_command("VAR='x y' gh pr view 1")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"

    def test_gh_exe_and_path_basename_parsed(self) -> None:
        """gh.exe (Windows) and absolute-path gh resolve by basename."""
        for cmd in ("gh.exe pr view 1", "/usr/local/bin/gh issue list", r"C:\bin\gh pr view 1"):
            assert parse_gh_command(cmd) is not None, cmd

    def test_quoted_separator_not_split(self) -> None:
        """A shell separator inside a quoted argument must not split the command
        and reintroduce the issue #2111 false positive."""
        assert parse_gh_command('python3 t.py --title "a | gh issue list"') is None
        assert parse_gh_command('echo x --body "... && gh pr view"') is None

    def test_pipe_ampersand_operator_segments(self) -> None:
        """The `|&` operator is one separator token; the gh after it is caught."""
        result = parse_gh_command("cmd |& gh pr view")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"

    def test_traversal_operands_rejected(self) -> None:
        """operation/action must be bare subcommand words so traversal operands
        like `..` never reach the path-joining skill lookup (CWE-22)."""
        assert parse_gh_command("gh .. ..") is None
        assert parse_gh_command("gh ../../etc passwd") is None
        assert parse_gh_command("gh pr ..") is None
        assert parse_gh_command("gh . view") is None
        # A traversal token as a later positional argument is fine; the real
        # subcommand words still resolve.
        assert parse_gh_command("gh pr view ..") is not None


class TestFindSkillScript:
    """Tests for skill script lookup."""

    def test_exact_mapping_found(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        script_file = script_dir / "get_pr_context.py"
        script_file.write_text("# stub")

        result = find_skill_script("pr", "view", str(tmp_path))
        assert result is not None
        assert result["path"] == str(script_file)

    def test_exact_mapping_script_missing(self, tmp_path: Path) -> None:
        """Mapping exists but file doesn't. Should return None."""
        result = find_skill_script("pr", "view", str(tmp_path))
        assert result is None

    def test_no_mapping(self, tmp_path: Path) -> None:
        result = find_skill_script("release", "create", str(tmp_path))
        assert result is None

    def test_fuzzy_match(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        script_file = script_dir / "get_pr_reviews.py"
        script_file.write_text("# stub")

        result = find_skill_script("pr", "reviews", str(tmp_path))
        assert result is not None
        assert "get_pr_reviews.py" in result["path"]

    def test_fuzzy_no_match(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)

        result = find_skill_script("pr", "nonexistent", str(tmp_path))
        assert result is None

    def test_unknown_operation_no_dir(self, tmp_path: Path) -> None:
        result = find_skill_script("unknown", "action", str(tmp_path))
        assert result is None


class TestWriteBlockResponse:
    """Tests for block response formatting."""

    def test_contains_blocked_command(self, capsys) -> None:
        write_block_response("gh pr create", "/path/to/skill", "python3 skill.py")
        captured = capsys.readouterr()
        assert "gh pr create" in captured.out
        assert "BLOCKED" in captured.out

    def test_contains_example(self, capsys) -> None:
        write_block_response("gh pr view 1", "/path", "python3 skill.py --pr 1")
        captured = capsys.readouterr()
        assert "python3 skill.py --pr 1" in captured.out


class TestSkillMappings:
    """Tests for skill mapping constants."""

    def test_pr_operations_exist(self) -> None:
        assert "pr" in SKILL_MAPPINGS
        assert len(SKILL_MAPPINGS["pr"]) >= 5

    def test_issue_operations_exist(self) -> None:
        assert "issue" in SKILL_MAPPINGS
        assert len(SKILL_MAPPINGS["issue"]) >= 3


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("invoke_skill_first_guard.skip_if_consumer_repo", return_value=False):
        yield


class TestMainAllow:
    """Tests for main() allowing commands."""

    def test_tty_stdin(self) -> None:
        with patch("invoke_skill_first_guard.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_non_gh_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"command": "ls -la"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_no_tool_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_name": "Bash"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_no_command_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"file_path": "/some/file"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_gh_command_no_skill(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh release create v1.0"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_invalid_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main() == 0

    def test_allows_non_gh_command_quoting_gh_subcommand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #2111 end to end: a python invocation that quotes 'gh issue list'
        is allowed even though an issue-list skill exists."""
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "issue"
        script_dir.mkdir(parents=True)
        (script_dir / "list_issues.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": 'python3 triage.py --body "gh issue list"'}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0


class TestMainBlock:
    """Tests for main() blocking commands."""

    def test_blocks_gh_pr_view_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "get_pr_context.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh pr view 123"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        result = main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Raw GitHub Command" in captured.out

    def test_blocks_gh_pr_create_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "new_pr.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh pr create --title test"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        assert main() == 2

    def test_blocks_gh_issue_view_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "issue"
        script_dir.mkdir(parents=True)
        (script_dir / "get_issue_context.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh issue view 456"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        assert main() == 2
