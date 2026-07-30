"""Tests for complete_session_log.py session completion script."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-end" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import complete_session_log


class TestGetRepoRoot:
    """Tests for _get_repo_root function (#3922)."""

    @patch("complete_session_log.subprocess.run")
    def test_returns_show_toplevel_output(self, mock_run):
        """Uses --show-toplevel so linked worktrees return their own root."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/tmp/wt_sess2\n")
        result = complete_session_log._get_repo_root()
        assert result == "/tmp/wt_sess2"
        # Verify the correct git subcommand is used
        call_args = mock_run.call_args[0][0]
        assert "--show-toplevel" in call_args
        assert "--git-common-dir" not in call_args

    @patch("complete_session_log.subprocess.run")
    def test_falls_back_when_git_fails(self, mock_run):
        """Returns a path derived from __file__ when git fails."""
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = complete_session_log._get_repo_root()
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("complete_session_log.subprocess.run")
    def test_linked_worktree_not_primary_root(self, mock_run):
        """--show-toplevel returns the worktree dir, not the primary root (#3922)."""
        # In a linked worktree /tmp/wt, --show-toplevel gives /tmp/wt.
        # --git-common-dir would give /primary/.git (primary repo's .git dir).
        mock_run.return_value = MagicMock(returncode=0, stdout="/tmp/wt\n")
        result = complete_session_log._get_repo_root()
        assert result == "/tmp/wt"


class TestReworkWarningShape:
    """Tests for reworkWarning Evidence field shape (#3929, #3954)."""

    def _make_session(self):
        return {"protocolCompliance": {"sessionEnd": {"reworkWarning": {}}}}

    @patch("complete_session_log._run_rework_warning_step")
    def test_evidence_written_as_string_not_list(self, mock_rework):
        """Evidence must be a string to satisfy the checklistItem schema (#3929)."""
        mock_rework.return_value = ("rework-warning: none", ["rework-warning: none"])
        session = self._make_session()
        session_end = session["protocolCompliance"]["sessionEnd"]

        # Simulate the relevant portion of main() that writes reworkWarning
        rework_summary, rework_evidence = complete_session_log._run_rework_warning_step()
        if "reworkWarning" not in session_end:
            session_end["reworkWarning"] = {}
        session_end["reworkWarning"]["level"] = "SHOULD"
        session_end["reworkWarning"]["Complete"] = True
        session_end["reworkWarning"]["Evidence"] = (
            "\n".join(rework_evidence)
            if isinstance(rework_evidence, list)
            else str(rework_evidence)
        )

        assert isinstance(session_end["reworkWarning"]["Evidence"], str)
        assert session_end["reworkWarning"]["level"] == "SHOULD"
        assert session_end["reworkWarning"]["Complete"] is True

    @patch("complete_session_log._run_rework_warning_step")
    def test_list_evidence_joined_with_newline(self, mock_rework):
        """Multi-line rework evidence is joined into a single string (#3954)."""
        lines = ["rework-warning: line1", "rework-warning: line2"]
        mock_rework.return_value = ("rework: 2 lines", lines)
        session = self._make_session()
        session_end = session["protocolCompliance"]["sessionEnd"]

        rework_summary, rework_evidence = complete_session_log._run_rework_warning_step()
        session_end["reworkWarning"]["level"] = "SHOULD"
        session_end["reworkWarning"]["Complete"] = True
        session_end["reworkWarning"]["Evidence"] = (
            "\n".join(rework_evidence)
            if isinstance(rework_evidence, list)
            else str(rework_evidence)
        )

        assert (
            session_end["reworkWarning"]["Evidence"]
            == "rework-warning: line1\nrework-warning: line2"
        )

    @patch("complete_session_log._run_rework_warning_step")
    def test_string_evidence_used_directly(self, mock_rework):
        """If rework step already returns a string, it is used as-is (#3954)."""
        mock_rework.return_value = ("rework: none", "rework-warning: none")
        session = self._make_session()
        session_end = session["protocolCompliance"]["sessionEnd"]

        rework_summary, rework_evidence = complete_session_log._run_rework_warning_step()
        session_end["reworkWarning"]["level"] = "SHOULD"
        session_end["reworkWarning"]["Complete"] = True
        session_end["reworkWarning"]["Evidence"] = (
            "\n".join(rework_evidence)
            if isinstance(rework_evidence, list)
            else str(rework_evidence)
        )

        assert session_end["reworkWarning"]["Evidence"] == "rework-warning: none"


class TestFindCurrentSessionLog:
    """Tests for _find_current_session_log function."""

    def test_returns_none_when_no_dir(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path / "missing")) is None

    def test_returns_none_when_empty(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path)) is None

    def test_finds_most_recent(self, tmp_path):
        f1 = tmp_path / "2026-01-01-session-1.json"
        f2 = tmp_path / "2026-01-02-session-2.json"
        f1.write_text("{}")
        f2.write_text("{}")
        result = complete_session_log._find_current_session_log(str(tmp_path))
        assert result is not None


class TestGetEndingCommit:
    """Tests for _get_ending_commit function."""

    @patch("complete_session_log.subprocess.run")
    def test_returns_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert complete_session_log._get_ending_commit() == "abc1234"

    @patch("complete_session_log.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert complete_session_log._get_ending_commit() is None


class TestHandoffModified:
    """Tests for _test_handoff_modified function."""

    @patch("complete_session_log.subprocess.run")
    def test_detects_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="HANDOFF.md\n")
        assert complete_session_log._test_handoff_modified() is True

    @patch("complete_session_log.subprocess.run")
    def test_not_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="other-file.md\n")
        assert complete_session_log._test_handoff_modified() is False


class TestSerenaMemoryUpdated:
    """Tests for _test_serena_memory_updated function."""

    @patch("complete_session_log.subprocess.run")
    def test_detects_memory_changes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=".serena/memories/test.md\n")
        assert complete_session_log._test_serena_memory_updated() is True

    @patch("complete_session_log.subprocess.run")
    def test_no_changes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="src/app.py\n")
        assert complete_session_log._test_serena_memory_updated() is False

    @patch("complete_session_log.subprocess.run")
    def test_detects_committed_memory_via_git_log(self, mock_run):
        """Committed .serena/memories/ changes are detected when starting_commit provided."""

        def _side_effect(cmd, **kwargs):
            if "log" in cmd:
                return MagicMock(returncode=0, stdout=".serena/memories/new.md\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _side_effect
        assert complete_session_log._test_serena_memory_updated("abc1234") is True

    @patch("complete_session_log.subprocess.run")
    def test_no_committed_memory_no_starting_commit(self, mock_run):
        """Without starting_commit, git log is not consulted (no false positive)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert complete_session_log._test_serena_memory_updated() is False
        for call in mock_run.call_args_list:
            assert "log" not in call.args[0]

    @patch("complete_session_log.subprocess.run")
    def test_committed_memory_unrelated_files_not_detected(self, mock_run):
        """git log output with no .serena/memories/ lines returns False."""

        def _side_effect(cmd, **kwargs):
            if "log" in cmd:
                return MagicMock(returncode=0, stdout="scripts/some_script.py\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _side_effect
        assert complete_session_log._test_serena_memory_updated("abc1234") is False

    @patch("complete_session_log.subprocess.run")
    def test_git_log_failure_returns_false(self, mock_run):
        """Non-zero git log exit code does not raise, returns False."""

        def _side_effect(cmd, **kwargs):
            if "log" in cmd:
                return MagicMock(returncode=128, stdout="")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _side_effect
        assert complete_session_log._test_serena_memory_updated("abc1234") is False


class TestUncommittedChanges:
    """Tests for _test_uncommitted_changes function."""

    @patch("complete_session_log.subprocess.run")
    def test_clean_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert complete_session_log._test_uncommitted_changes() is False

    @patch("complete_session_log.subprocess.run")
    def test_dirty_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.py\n")
        assert complete_session_log._test_uncommitted_changes() is True


class TestPathContainment:
    """Tests for _validate_path_containment (CWE-22)."""

    def test_valid_path(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "test.json"
        session_file.write_text("{}")
        result = complete_session_log._validate_path_containment(
            str(session_file), str(sessions_dir)
        )
        assert result is not None

    def test_rejects_traversal(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        evil_path = tmp_path / "evil.json"
        evil_path.write_text("{}")
        result = complete_session_log._validate_path_containment(str(evil_path), str(sessions_dir))
        assert result is None


class TestRunMarkdownLint:
    """Tests for _run_markdown_lint function."""

    @patch("complete_session_log.subprocess.run")
    def test_no_markdown_files(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="src/app.py\n")
        success, output = complete_session_log._run_markdown_lint()
        assert success is True
        assert "No markdown" in output


class TestMainReworkWarningShape:
    """Integration: main() writes reworkWarning.Evidence as a string, not a list (#3929, #3954)."""

    def _make_session_json(self, path):
        """Write a minimal valid session JSON to path."""
        import json

        data = {
            "session": {
                "number": 99,
                "date": "2026-07-30",
                "branch": "fix/test",
                "startingCommit": "abc1234",
                "objective": "test",
            },
            "protocolCompliance": {
                "sessionStart": {},
                "sessionEnd": {
                    "handoffPreserved": {
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "serenaMemoryUpdated": {
                        "level": "SHOULD",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "markdownLintRun": {
                        "level": "SHOULD",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "reworkWarning": {
                        "level": "SHOULD",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "changesCommitted": {
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "validationPassed": {
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "checklistComplete": {
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                },
            },
        }
        path.write_text(json.dumps(data, indent=2))
        return data

    @patch("complete_session_log.subprocess.run")
    @patch("complete_session_log._run_rework_warning_step")
    @patch("complete_session_log._run_markdown_lint")
    @patch("complete_session_log._test_serena_memory_updated")
    @patch("complete_session_log._test_handoff_modified")
    @patch("complete_session_log._get_ending_commit")
    @patch("complete_session_log._test_uncommitted_changes")
    @patch("complete_session_log._get_repo_root")
    def test_rework_evidence_is_string_in_output(
        self,
        mock_root,
        mock_uncommitted,
        mock_commit,
        mock_handoff,
        mock_serena,
        mock_lint,
        mock_rework,
        mock_subprocess,
        tmp_path,
    ):
        """main() writes Evidence as a string, never a list (#3929, #3954)."""
        import json

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / "2026-07-30-session-99-test.json"
        self._make_session_json(session_file)

        mock_root.return_value = str(tmp_path)
        mock_uncommitted.return_value = False
        mock_commit.return_value = "abc1234"
        mock_handoff.return_value = False
        mock_serena.return_value = True
        mock_lint.return_value = (True, "lint passed")
        mock_rework.return_value = ("rework: none", ["rework-warning: none", "extra line"])
        # subprocess.run is for the final validate step; skip it
        mock_subprocess.return_value = MagicMock(returncode=0)

        with patch(
            "complete_session_log.resolve_artifact_root",
            return_value=sessions_dir,
        ):
            exit_code = complete_session_log.main(["--session-path", str(session_file)])

        assert exit_code == 0
        result = json.loads(session_file.read_text())
        evidence = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]["Evidence"]
        assert isinstance(evidence, str), f"Evidence must be a string, got {type(evidence)}"
        assert "rework-warning: none" in evidence
