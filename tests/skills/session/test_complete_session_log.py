# taste-lint: ignore file-size, session-end QA contract shares fixtures.
"""Tests for complete_session_log.py session completion script."""

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts"
SESSION_INIT_DIR = REPO_ROOT / ".claude" / "skills" / "session-init"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SESSION_INIT_DIR))

import complete_session_log
from session_init.session_structure import build_session_log

from scripts.validate_session_json import (
    SESSION_END_REQUIRED_ITEMS,
    ValidationResult,
    validate_must_item,
)


class TestQaValidationContract:
    """Regression coverage for the session-init to session-end QA contract."""

    def test_qa_session_identity_supports_external_artifact_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        artifact_root = tmp_path / "artifacts"
        session_path = artifact_root / "sessions" / "session.json"
        session_path.parent.mkdir(parents=True)
        session_path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv(
            "AI_AGENTS_ARTIFACT_ROOT",
            str(artifact_root),
        )

        identity = complete_session_log._qa_session_log_identity(
            str(session_path),
            str(tmp_path),
        )

        assert identity == ".agents/sessions/session.json"

    def test_new_session_declares_required_qa_validation(self):
        log = build_session_log(
            branch="fix/test",
            commit="a" * 40,
            session_number=1,
            objective="test",
            current_date="2026-08-07",
        )

        qa = log["protocolCompliance"]["sessionEnd"]["qaValidation"]

        assert qa == {"level": "MUST", "Complete": False, "Evidence": ""}
        assert "qaValidation" in SESSION_END_REQUIRED_ITEMS

    def test_policy_qa_skips_do_not_contradict_completion(self):
        for evidence in ("SKIPPED: docs-only", "SKIPPED: investigation-only"):
            result = ValidationResult()

            validate_must_item(
                {"level": "MUST", "Complete": True, "Evidence": evidence},
                "qaValidation",
                "sessionEnd",
                result,
                is_required=True,
            )

            assert result.errors == []
            assert result.warnings == []

    def test_unapproved_qa_skip_fails_validation(self):
        result = ValidationResult()

        validate_must_item(
            {"level": "MUST", "Complete": True, "Evidence": "SKIPPED: feature-code"},
            "qaValidation",
            "sessionEnd",
            result,
            is_required=True,
        )

        assert any("Evidence contradiction" in error for error in result.errors)

    def test_qa_report_and_skip_reason_are_mutually_exclusive(self):
        parser = complete_session_log.build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--qa-report",
                    ".agents/qa/report.md",
                    "--qa-skip-reason",
                    "investigation-only",
                ]
            )


class TestGetRepoRoot:

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


class TestFindCurrentSessionLog:

    def test_returns_none_when_no_dir(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path / "missing")) is None

    def test_returns_none_when_empty(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path)) is None

    def test_finds_most_recent(self, tmp_path):
        import json
        import os

        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        f1 = tmp_path / f"{today}-session-1.json"
        f2 = tmp_path / f"{today}-session-2.json"
        branch = "feature/test"
        f1.write_text(json.dumps({"session": {"branch": branch}}))
        f2.write_text(json.dumps({"session": {"branch": branch}}))
        # Make the ordering deterministic: f2 is the newest branch match.
        os.utime(f1, (1000, 1000))
        os.utime(f2, (2000, 2000))
        with patch("complete_session_log._get_current_branch", return_value=branch):
            result = complete_session_log._find_current_session_log(str(tmp_path))
        assert result == str(f2)

    def test_finds_most_recent_ignores_older_mtime_match(self, tmp_path):
        """The newest branch match wins even when the older file sorts first by name."""
        import json
        import os

        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        f1 = tmp_path / f"{today}-session-1.json"
        f2 = tmp_path / f"{today}-session-2.json"
        branch = "feature/test"
        f1.write_text(json.dumps({"session": {"branch": branch}}))
        f2.write_text(json.dumps({"session": {"branch": branch}}))
        os.utime(f1, (2000, 2000))
        os.utime(f2, (1000, 1000))
        with patch("complete_session_log._get_current_branch", return_value=branch):
            result = complete_session_log._find_current_session_log(str(tmp_path))
        assert result == str(f1)


class TestGetEndingCommit:

    @patch("complete_session_log.subprocess.run")
    def test_returns_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert complete_session_log._get_ending_commit() == "abc1234"

    @patch("complete_session_log.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert complete_session_log._get_ending_commit() is None


class TestSetEndingCommit:
    """Tests for ending commit and episode boundary alignment."""

    def test_refresh_aligns_short_commit_and_full_comparison_head(self):
        full_commit = "a" * 40
        session = {
            "endingCommit": "old1234",
            "episodeMetrics": {
                "comparison": {
                    "kind": "gitCommitRange",
                    "base": "b" * 40,
                    "head": "c" * 40,
                }
            },
        }

        complete_session_log._set_ending_commit(
            session,
            full_commit,
            refresh=True,
        )

        assert session["endingCommit"] == "a" * 10
        assert session["episodeMetrics"]["comparison"]["head"] == full_commit


class TestHandoffModified:

    @patch("complete_session_log.subprocess.run")
    def test_detects_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="HANDOFF.md\n")
        assert complete_session_log._test_handoff_modified() is True

    @patch("complete_session_log.subprocess.run")
    def test_not_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="other-file.md\n")
        assert complete_session_log._test_handoff_modified() is False


class TestSerenaMemoryUpdated:

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

    @patch("complete_session_log.subprocess.run")
    def test_memories_backup_dir_not_detected(self, mock_run):
        """Path .serena/memories_backup must not be confused with .serena/memories/."""
        mock_run.return_value = MagicMock(returncode=0, stdout=".serena/memories_backup/old.md\n")
        assert complete_session_log._test_serena_memory_updated() is False

    @patch("complete_session_log.subprocess.run")
    def test_memories_backup_in_git_log_not_detected(self, mock_run):
        """committed .serena/memories_backup changes must not fire the check."""

        def _side_effect(cmd, **kwargs):
            if "log" in cmd:
                return MagicMock(returncode=0, stdout=".serena/memories_backup/old.md\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _side_effect
        assert complete_session_log._test_serena_memory_updated("abc1234") is False


class TestUncommittedChanges:

    @patch("complete_session_log.subprocess.run")
    def test_clean_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert complete_session_log._test_uncommitted_changes() is False

    @patch("complete_session_log.subprocess.run")
    def test_dirty_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.py\n")
        assert complete_session_log._test_uncommitted_changes() is True

    @patch("complete_session_log.subprocess.run")
    def test_exclude_path_hides_session_log(self, mock_run):
        """Excluding the session log makes changesCommitted satisfiable (#4425)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M .agents/sessions/2026-08-03-session-0001.json\n",
        )
        assert (
            complete_session_log._test_uncommitted_changes(
                exclude_path=".agents/sessions/2026-08-03-session-0001.json"
            )
            is False
        )

    @patch("complete_session_log.subprocess.run")
    def test_exclude_path_does_not_hide_other_changes(self, mock_run):
        """Other dirty files are still detected when session log is excluded."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                " M .agents/sessions/2026-08-03-session-0001.json\n"
                " M scripts/validation/checks_common.py\n"
            ),
        )
        assert (
            complete_session_log._test_uncommitted_changes(
                exclude_path=".agents/sessions/2026-08-03-session-0001.json"
            )
            is True
        )

    @patch("complete_session_log.subprocess.run")
    def test_no_exclude_path_still_reports_dirty(self, mock_run):
        """Omitting exclude_path preserves original behaviour."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M .agents/sessions/2026-08-03-session-0001.json\n",
        )
        assert complete_session_log._test_uncommitted_changes() is True


class TestMainNormalizesExcludePathToRelative:
    def _run(self, tmp_path, *, rp=None, win=False):
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        sf = sessions / "2026-08-06-session-1-test.json"
        TestMainReworkWarningShape._make_session_json(self, sf)
        captured: list[str | None] = []
        patches = [
            patch("complete_session_log._get_repo_root", return_value=str(tmp_path)),
            patch("complete_session_log._get_ending_commit", return_value="a1"),
            patch("complete_session_log._test_handoff_modified", return_value=False),
            patch("complete_session_log._test_serena_memory_updated", return_value=True),
            patch("complete_session_log._run_markdown_lint", return_value=(True, "")),
            patch("complete_session_log._run_rework_warning_step", return_value=("", "")),
            patch("complete_session_log.subprocess.run", return_value=MagicMock(returncode=0)),
            patch(
                "complete_session_log._test_uncommitted_changes",
                side_effect=lambda exclude_path=None, *, exclude_paths=(): (
                    captured.append(exclude_path or next(iter(exclude_paths), None)),
                    False,
                )[1],
            ),
            patch("complete_session_log.resolve_artifact_root", return_value=sessions),
            patch("complete_session_log._validate_path_containment", side_effect=lambda p, d: p)]
        if rp is not None:
            patches.append(patch("complete_session_log.os.path.relpath", **rp))
        if win:
            patches.append(patch.object(os, "sep", "\\"))
        with ExitStack() as s:
            [s.enter_context(p) for p in patches]
            complete_session_log.main(["--session-path", str(sf)])
        return captured[0] if captured else "NOT_CALLED"
    def test_in_repo_path_is_excluded(self, tmp_path):
        expected = os.path.join(".agents", "sessions", "2026-08-06-session-1-test.json")
        assert self._run(tmp_path) == expected
    def test_dotdot_prefixed_name_inside_repo_is_excluded(self, tmp_path):
        val = os.path.join("..foo", "sessions", "s.json")
        assert self._run(tmp_path, rp={"return_value": val}) == val
    def test_actual_parent_traversal_yields_none(self, tmp_path):
        val = os.path.join("..", "outside", "s.json")
        assert self._run(tmp_path, rp={"return_value": val}) is None
    def test_cross_drive_valueerror_yields_none(self, tmp_path):
        assert self._run(tmp_path, rp={"side_effect": ValueError("D:")}) is None
    def test_win_parent_traversal_yields_none(self, tmp_path):
        assert self._run(tmp_path, rp={"return_value": r"..\outside\s.json"}, win=True) is None
        v = r"..foo\s.json"  # valid name, not parent traversal
        assert self._run(tmp_path, rp={"return_value": v}, win=True) == v


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

    @patch.object(complete_session_log, "_changed_markdown_files", return_value=set())
    def test_no_markdown_files(self, _mock_changed_files):
        success, output = complete_session_log._run_markdown_lint()

        assert success is True
        assert output == "NOT LINTED: no changed markdown files"


class TestMainReworkWarningShape:
    """Integration: main() writes reworkWarning.Evidence as a string, not a list (#3929, #3954)."""

    COMMIT = "a" * 40

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
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "markdownLintRun": {
                        "level": "MUST",
                        "Complete": False,
                        "Evidence": "",
                    },
                    "qaValidation": {
                        "level": "MUST",
                        "Complete": True,
                        "Evidence": "SKIPPED: investigation-only",
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

    def test_owned_evidence_includes_session_qa_and_episode(self, tmp_path):
        session_path = (
            tmp_path
            / ".agents"
            / "sessions"
            / "2026-07-30-session-99-test.json"
        )

        paths = complete_session_log._owned_evidence_paths(
            str(session_path),
            str(tmp_path),
            ".agents/qa/report.md",
        )

        assert paths == [
            ".agents/sessions/2026-07-30-session-99-test.json",
            ".agents/qa/report.md",
            ".agents/memory/episodes/episode-2026-07-30-session-99-test.json",
        ]

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
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("", encoding="utf-8")

        mock_root.return_value = str(tmp_path)
        mock_uncommitted.return_value = False
        mock_commit.return_value = "abc1234"
        mock_handoff.return_value = False
        mock_serena.return_value = True
        mock_lint.return_value = (True, "lint passed")
        mock_rework.return_value = ("rework: none", ["rework-warning: none", "extra line"])

        def validate_saved_state(*run_args, **_kwargs):
            command = run_args[0]
            assert command[-2:] == ["--validation-head", "abc1234"]
            saved = json.loads(session_file.read_text())
            session_end = saved["protocolCompliance"]["sessionEnd"]
            assert session_end["validationPassed"]["Complete"] is True
            assert session_end["checklistComplete"]["Complete"] is True
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = validate_saved_state

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

    @staticmethod
    def _write_qa_report(
        path,
        *,
        verdict="PASS",
        session_log=".agents/sessions/2026-07-30-session-99-test.json",
        commit=None,
    ):
        path.write_text(
            "---\n"
            f"qaVerdict: {verdict}\n"
            f"qaSessionLog: {session_log}\n"
            f"qaCommit: {commit or TestMainReworkWarningShape.COMMIT}\n"
            "---\n"
            "# QA\n",
            encoding="utf-8",
        )

    def _run_main_with_rework(
        self,
        tmp_path,
        rework_return,
        extra_args=None,
        *,
        ending_commit="abc1234",
    ):
        """Helper: run main() with a controlled rework step return value."""
        import json

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / "2026-07-30-session-99-test.json"
        self._make_session_json(session_file)
        validator = tmp_path / "scripts" / "validate_session_json.py"
        validator.parent.mkdir(parents=True)
        validator.write_text("", encoding="utf-8")

        with (
            patch("complete_session_log._get_repo_root", return_value=str(tmp_path)),
            patch("complete_session_log._test_uncommitted_changes", return_value=False),
            patch("complete_session_log._get_ending_commit", return_value=ending_commit),
            patch("complete_session_log._test_handoff_modified", return_value=False),
            patch("complete_session_log._test_serena_memory_updated", return_value=True),
            patch("complete_session_log._run_markdown_lint", return_value=(True, "ok")),
            patch("complete_session_log._run_rework_warning_step", return_value=rework_return),
            patch("complete_session_log.subprocess.run", return_value=MagicMock(returncode=0)),
            patch("complete_session_log.resolve_artifact_root", return_value=sessions_dir),
        ):
            exit_code = complete_session_log.main(
                ["--session-path", str(session_file), *(extra_args or [])]
            )

        self.last_exit_code = exit_code
        return json.loads(session_file.read_text())

    def test_main_records_validated_qa_report(self, tmp_path):
        report = tmp_path / ".agents" / "qa" / "report.md"
        report.parent.mkdir(parents=True)
        self._write_qa_report(report)

        result = self._run_main_with_rework(
            tmp_path,
            ("Rework warning: none", ["rework-warning: none"]),
            ["--qa-report", str(report)],
            ending_commit=self.COMMIT,
        )

        assert self.last_exit_code == 0
        qa = result["protocolCompliance"]["sessionEnd"]["qaValidation"]
        assert qa == {
            "level": "MUST",
            "Complete": True,
            "Evidence": ".agents/qa/report.md",
        }

    @pytest.mark.parametrize(
        ("verdict", "session_log", "commit"),
        [
            (
                "DEFERRED",
                ".agents/sessions/2026-07-30-session-99-test.json",
                COMMIT,
            ),
            (
                "FAIL",
                ".agents/sessions/2026-07-30-session-99-test.json",
                COMMIT,
            ),
            ("PASS", ".agents/sessions/unrelated.json", COMMIT),
        ],
    )
    def test_main_rejects_unbound_or_non_passing_qa_report(
        self,
        tmp_path,
        verdict,
        session_log,
        commit,
    ):
        report = tmp_path / ".agents" / "qa" / "report.md"
        report.parent.mkdir(parents=True)
        self._write_qa_report(
            report,
            verdict=verdict,
            session_log=session_log,
            commit=commit,
        )

        self._run_main_with_rework(
            tmp_path,
            ("Rework warning: none", ["rework-warning: none"]),
            ["--qa-report", str(report)],
            ending_commit=self.COMMIT,
        )

        assert self.last_exit_code == 1

    def test_main_accepts_mismatched_commit_when_only_evidence_changed(self, tmp_path):
        # ADR-096: a qaCommit that differs from the session's endingCommit no
        # longer hard-fails on its own. _run_main_with_rework's shared
        # subprocess.run mock (patched on the single global `subprocess`
        # module object, so it also intercepts qa_report.post_qa_code_changes'
        # git calls) returns returncode=0 with a MagicMock stdout; iterating
        # a bare MagicMock yields zero items, so post_qa_code_changes sees an
        # empty (evidence-only) change set and the mismatch is accepted.
        report = tmp_path / ".agents" / "qa" / "report.md"
        report.parent.mkdir(parents=True)
        self._write_qa_report(report, commit="b" * 40)

        self._run_main_with_rework(
            tmp_path,
            ("Rework warning: none", ["rework-warning: none"]),
            ["--qa-report", str(report)],
            ending_commit=self.COMMIT,
        )

        assert self.last_exit_code == 0

    def test_main_rejects_mismatched_commit_when_real_code_changed(self, tmp_path):
        # ADR-096: the case that must still hard-fail. Real code changed
        # between the QA-validated commit and the session's endingCommit.
        report = tmp_path / ".agents" / "qa" / "report.md"
        report.parent.mkdir(parents=True)
        self._write_qa_report(report, commit="b" * 40)

        ancestor_ok = MagicMock(returncode=0)
        real_change = MagicMock(returncode=0, stdout="scripts/changed.py\0")

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / "2026-07-30-session-99-test.json"
        self._make_session_json(session_file)

        with (
            patch("complete_session_log._get_repo_root", return_value=str(tmp_path)),
            patch("complete_session_log._test_uncommitted_changes", return_value=False),
            patch(
                "complete_session_log._get_ending_commit", return_value=self.COMMIT
            ),
            patch("complete_session_log._test_handoff_modified", return_value=False),
            patch("complete_session_log._test_serena_memory_updated", return_value=True),
            patch("complete_session_log._run_markdown_lint", return_value=(True, "ok")),
            patch(
                "complete_session_log._run_rework_warning_step",
                return_value=("Rework warning: none", ["rework-warning: none"]),
            ),
            patch(
                "complete_session_log.subprocess.run",
                side_effect=[ancestor_ok, real_change],
            ),
            patch("complete_session_log.resolve_artifact_root", return_value=sessions_dir),
        ):
            exit_code = complete_session_log.main(
                ["--session-path", str(session_file), "--qa-report", str(report)]
            )

        assert exit_code == 1

    def test_main_records_policy_qa_skip(self, tmp_path):
        with patch(
            "complete_session_log._investigation_skip_evidence",
            return_value="SKIPPED: investigation-only",
        ):
            result = self._run_main_with_rework(
                tmp_path,
                ("Rework warning: none", ["rework-warning: none"]),
                ["--qa-skip-reason", "investigation-only"],
            )

        assert self.last_exit_code == 0
        qa = result["protocolCompliance"]["sessionEnd"]["qaValidation"]
        assert qa == {
            "level": "MUST",
            "Complete": True,
            "Evidence": "SKIPPED: investigation-only",
        }

    def test_main_fails_when_validator_is_missing(self, tmp_path):
        import json

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / "2026-07-30-session-99-test.json"
        self._make_session_json(session_file)

        with (
            patch("complete_session_log._get_repo_root", return_value=str(tmp_path)),
            patch("complete_session_log._test_uncommitted_changes", return_value=False),
            patch("complete_session_log._get_ending_commit", return_value="abc1234"),
            patch("complete_session_log._test_handoff_modified", return_value=False),
            patch("complete_session_log._test_serena_memory_updated", return_value=True),
            patch("complete_session_log._run_markdown_lint", return_value=(True, "ok")),
            patch(
                "complete_session_log._run_rework_warning_step",
                return_value=("Rework warning: none", ["rework-warning: none"]),
            ),
            patch("complete_session_log.resolve_artifact_root", return_value=sessions_dir),
        ):
            exit_code = complete_session_log.main(
                ["--session-path", str(session_file)]
            )

        result = json.loads(session_file.read_text())
        session_end = result["protocolCompliance"]["sessionEnd"]
        assert exit_code == 1
        assert session_end["validationPassed"]["Complete"] is False
        assert session_end["checklistComplete"]["Complete"] is False

    def test_investigation_skip_rejects_disallowed_changes(self, tmp_path):
        completed = MagicMock(
            returncode=0,
            stdout='{"Eligible": false, "Violations": ["scripts/main.py"]}',
        )

        with patch("complete_session_log.subprocess.run", return_value=completed):
            with pytest.raises(ValueError, match="scripts/main.py"):
                complete_session_log._investigation_skip_evidence(
                    tmp_path,
                    "a" * 40,
                )

    def test_rework_complete_true_when_step_runs(self, tmp_path):
        """Complete=True when rework step ran without skipping (post-#4001)."""
        result = self._run_main_with_rework(
            tmp_path, ("Rework warning: none", ["rework-warning: none"])
        )
        rw = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]
        assert rw["Complete"] is True

    def test_rework_complete_false_when_sibling_unavailable(self, tmp_path):
        """Complete=False when rework step was skipped due to missing module (post-#4001)."""
        result = self._run_main_with_rework(
            tmp_path,
            (
                "Rework warning: skipped (sibling unavailable)",
                ["rework-warning: skipped (sibling module unavailable)"],
            ),
        )
        rw = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]
        assert rw["Complete"] is False

    def test_rework_complete_false_when_runtime_error(self, tmp_path):
        """Complete=False when rework step was skipped due to runtime error (post-#4001)."""
        result = self._run_main_with_rework(
            tmp_path,
            (
                "Rework warning: skipped (runtime error)",
                ["rework-warning: skipped (runtime error: OSError)"],
            ),
        )
        rw = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]
        assert rw["Complete"] is False

    def test_rework_evidence_joined_when_multiline(self, tmp_path):
        """Multi-line evidence is joined with newline into a single string (post-#4001)."""
        result = self._run_main_with_rework(
            tmp_path,
            ("[WARN] rework warning: 2 file(s)", ["rework-warning: a.py", "rework-warning: b.py"]),
        )
        rw = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]
        assert rw["Evidence"] == "rework-warning: a.py\nrework-warning: b.py"

    def test_rework_evidence_string_passthrough(self, tmp_path):
        """String evidence (not a list) is stored as-is (post-#4001)."""
        result = self._run_main_with_rework(
            tmp_path, ("Rework warning: none", "rework-warning: none (string form)")
        )
        rw = result["protocolCompliance"]["sessionEnd"]["reworkWarning"]
        assert rw["Evidence"] == "rework-warning: none (string form)"
