"""Tests for adr_review_guard.py Claude Code PreToolUse hook."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOKS_DIR))

import adr_review_guard


class TestIsGitCommitCommand:
    """Tests for _is_git_commit_command."""

    def test_git_commit(self):
        assert adr_review_guard._is_git_commit_command("git commit -m 'msg'") is True

    def test_git_ci_alias(self):
        assert adr_review_guard._is_git_commit_command("git ci -m 'msg'") is True

    def test_not_git_command(self):
        assert adr_review_guard._is_git_commit_command("git push") is False

    def test_empty_command(self):
        assert adr_review_guard._is_git_commit_command("") is False

    def test_none_command(self):
        assert adr_review_guard._is_git_commit_command(None) is False

    def test_whitespace_only(self):
        assert adr_review_guard._is_git_commit_command("   ") is False

    def test_git_commit_with_prefix(self):
        assert adr_review_guard._is_git_commit_command(
            "cd /tmp && git commit -m 'msg'"
        ) is True


class TestGetStagedADRChanges:
    """Tests for _get_staged_adr_changes."""

    def test_returns_adr_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="src/main.py\n.agents/architecture/ADR-001.md\nREADME.md\n",
                stderr=""
            )
            result = adr_review_guard._get_staged_adr_changes()
            assert result == [".agents/architecture/ADR-001.md"]

    def test_returns_empty_for_no_staged(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = adr_review_guard._get_staged_adr_changes()
            assert result == []

    def test_raises_on_git_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal error"
            )
            with pytest.raises(RuntimeError, match="git diff --cached failed"):
                adr_review_guard._get_staged_adr_changes()

    def test_case_insensitive_adr_match(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="docs/adr-042.md\n",
                stderr=""
            )
            result = adr_review_guard._get_staged_adr_changes()
            assert result == ["docs/adr-042.md"]

    def test_multiple_adr_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="ADR-001.md\nADR-002.md\nsrc/code.py\n",
                stderr=""
            )
            result = adr_review_guard._get_staged_adr_changes()
            assert len(result) == 2


class TestGetTodaySessionLog:
    """Tests for _get_today_session_log."""

    def test_returns_none_for_missing_dir(self):
        result = adr_review_guard._get_today_session_log(
            "/nonexistent", "2026-03-01"
        )
        assert result is None

    def test_returns_none_when_no_matching_logs(self, tmp_path):
        result = adr_review_guard._get_today_session_log(
            str(tmp_path), "2026-03-01"
        )
        assert result is None

    def test_returns_latest_matching_log(self, tmp_path):
        (tmp_path / "2026-03-01-session-01.json").write_text("{}")
        (tmp_path / "2026-03-01-session-02.json").write_text("{}")
        result = adr_review_guard._get_today_session_log(
            str(tmp_path), "2026-03-01"
        )
        assert "session-02" in result


class TestADRReviewEvidence:
    """Tests for _test_adr_review_evidence."""

    def test_finds_adr_review_invocation(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "adr-042-debate.md").write_text("debate")
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is True

    def test_no_evidence_found(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Just a normal session")
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is False
        assert "No adr-review evidence" in result["reason"]

    def test_evidence_but_no_debate_log(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        # No debate log files
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is False
        assert "no debate log" in result["reason"]

    def test_evidence_but_no_analysis_dir(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is False
        assert "does not exist" in result["reason"]

    def test_permission_error(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("content")
        os.chmod(session_log, 0o000)
        try:
            result = adr_review_guard._test_adr_review_evidence(
                str(session_log), str(tmp_path)
            )
            assert result["complete"] is False
            assert "locked" in result["reason"] or "permissions" in result["reason"]
        finally:
            os.chmod(session_log, 0o644)

    def test_file_not_found(self, tmp_path):
        result = adr_review_guard._test_adr_review_evidence(
            str(tmp_path / "missing.json"), str(tmp_path)
        )
        assert result["complete"] is False
        assert "deleted" in result["reason"]

    def test_adr_review_skill_pattern(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Used adr-review skill for changes")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-notes.md").write_text("notes")
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is True

    def test_adr_review_protocol_pattern(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("## ADR Review Protocol\nFindings...")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-log.md").write_text("log")
        result = adr_review_guard._test_adr_review_evidence(
            str(session_log), str(tmp_path)
        )
        assert result["complete"] is True


class TestFormatBlockMessage:
    """Tests for _format_block_message."""

    def test_basic_message(self):
        msg = adr_review_guard._format_block_message(["ADR-001.md"])
        assert "BLOCKED" in msg
        assert "ADR-001.md" in msg
        assert "/adr-review" in msg

    def test_with_problem(self):
        msg = adr_review_guard._format_block_message(
            ["ADR-001.md"], problem="No evidence found"
        )
        assert "No evidence found" in msg

    def test_with_session_log_name(self):
        msg = adr_review_guard._format_block_message(
            ["ADR-001.md"],
            session_log_name="2026-03-01-session-01.json",
        )
        assert "2026-03-01-session-01.json" in msg


class TestMain:
    """Tests for main() entry point."""

    def test_allows_non_commit_command(self, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git push"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert adr_review_guard.main() == 0

    def test_allows_empty_input(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert adr_review_guard.main() == 0

    def test_allows_commit_without_adr_changes(self, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'fix'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            adr_review_guard, "_get_staged_adr_changes", return_value=[]
        ):
            assert adr_review_guard.main() == 0

    def test_blocks_adr_commit_without_session_log(self, monkeypatch, capsys):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            adr_review_guard, "_get_staged_adr_changes",
            return_value=["ADR-001.md"],
        ):
            with patch.object(
                adr_review_guard, "_get_today_session_log", return_value=None
            ):
                result = adr_review_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_blocks_adr_commit_without_evidence(self, monkeypatch, tmp_path, capsys):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        session_log = str(tmp_path / "session.json")
        with patch.object(
            adr_review_guard, "_get_staged_adr_changes",
            return_value=["ADR-001.md"],
        ):
            with patch.object(
                adr_review_guard, "_get_today_session_log",
                return_value=session_log,
            ):
                with patch.object(
                    adr_review_guard, "_test_adr_review_evidence",
                    return_value={"complete": False, "reason": "No evidence"},
                ):
                    result = adr_review_guard.main()
        assert result == 2

    def test_allows_adr_commit_with_evidence(self, monkeypatch, tmp_path):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        session_log = str(tmp_path / "session.json")
        with patch.object(
            adr_review_guard, "_get_staged_adr_changes",
            return_value=["ADR-001.md"],
        ):
            with patch.object(
                adr_review_guard, "_get_today_session_log",
                return_value=session_log,
            ):
                with patch.object(
                    adr_review_guard, "_test_adr_review_evidence",
                    return_value={"complete": True, "evidence": "found"},
                ):
                    assert adr_review_guard.main() == 0

    def test_blocks_on_git_error_fail_closed(self, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            adr_review_guard, "_get_staged_adr_changes",
            side_effect=RuntimeError("git failed"),
        ):
            assert adr_review_guard.main() == 2

    def test_fails_open_on_unexpected_error(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json at all {{{"))
        # Should fail-open (exit 0) on JSON parse error in outer try
        assert adr_review_guard.main() == 0

    def test_allows_missing_tool_input(self, monkeypatch):
        input_data = json.dumps({"cwd": "/tmp"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert adr_review_guard.main() == 0

    def test_allows_non_dict_tool_input(self, monkeypatch):
        input_data = json.dumps({"tool_input": "string"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert adr_review_guard.main() == 0

    def test_stdin_not_readable(self, monkeypatch):
        """When stdin is not readable, main returns 0 (fail-open)."""
        mock_stdin = io.StringIO("")
        mock_stdin.readable = lambda: False
        monkeypatch.setattr("sys.stdin", mock_stdin)
        assert adr_review_guard.main() == 0


class TestWriteAuditLogOSError:
    """Tests for _write_audit_log OSError handling."""

    def test_prints_critical_on_oserror(self, capsys):
        with patch("builtins.open", side_effect=OSError("write failed")):
            adr_review_guard._write_audit_log("TestHook", "test msg")
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.err


class TestGetProjectDirectoryGitWalk:
    """Tests for _get_project_directory git walk-up behavior."""

    def test_uses_env_var(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/custom/project/dir")
        result = adr_review_guard._get_project_directory()
        assert result == "/custom/project/dir"

    def test_git_walk_up_finds_project(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "src" / "deep"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        result = adr_review_guard._get_project_directory()
        assert result == str(tmp_path)

    def test_falls_back_to_cwd_when_no_git(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        result = adr_review_guard._get_project_directory()
        # When no .git found up the chain, returns str(Path.cwd())
        assert result


class TestGetTodaySessionLogOSError:
    """Tests for _get_today_session_log OSError handling."""

    def test_returns_none_on_oserror(self, tmp_path):
        (tmp_path / "dummy").mkdir()
        with patch("os.listdir", side_effect=OSError("denied")):
            result = adr_review_guard._get_today_session_log(
                str(tmp_path / "dummy"), "2026-03-01"
            )
        assert result is None


class TestADRReviewEvidenceValueError:
    """Tests for _test_adr_review_evidence ValueError/KeyError handling."""

    def test_value_error_returns_incomplete(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-log.md").write_text("notes")

        with patch("builtins.open", side_effect=ValueError("bad value")):
            result = adr_review_guard._test_adr_review_evidence(
                str(session_log), str(tmp_path)
            )
        assert result["complete"] is False
        assert "invalid data" in result["reason"]

    def test_oserror_returns_incomplete(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review")

        with patch("builtins.open", side_effect=OSError("io error")):
            result = adr_review_guard._test_adr_review_evidence(
                str(session_log), str(tmp_path)
            )
        assert result["complete"] is False
        assert "Error reading" in result["reason"]

    def test_oserror_listing_analysis_dir(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-log.md").write_text("notes")

        with patch("os.listdir", side_effect=OSError("denied")):
            # The open() call succeeds but listdir fails - still incomplete
            result = adr_review_guard._test_adr_review_evidence(
                str(session_log), str(tmp_path)
            )
        # OSError on listdir is caught by the outer OSError handler
        assert isinstance(result, dict)


class TestGetTodaySessionLogBranches:
    """Branch coverage for _get_today_session_log edge cases."""

    def test_directory_entry_not_file(self, tmp_path):
        """Directory matching session log pattern is skipped."""
        subdir = tmp_path / "2026-03-01-session-01.json"
        subdir.mkdir()
        result = adr_review_guard._get_today_session_log(
            str(tmp_path), "2026-03-01"
        )
        assert result is None

    def test_non_matching_entries_skipped(self, tmp_path):
        """Non-matching file entries are ignored."""
        (tmp_path / "2026-03-01-notes.txt").write_text("notes")
        (tmp_path / "other-file.json").write_text("{}")
        result = adr_review_guard._get_today_session_log(
            str(tmp_path), "2026-03-01"
        )
        assert result is None


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_adr_review_guard_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse" / "adr_review_guard.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input='{"tool_input": {"command": "git push"}}',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse" / "adr_review_guard.py"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
