#!/usr/bin/env python3
"""Tests for session-end skill complete_session_log.py."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "complete_session_log.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("complete_session_log", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sessions_dir(tmp_path):
    return str(_load_module().artifact_dir("sessions", base=tmp_path))


def _session_log(mod):
    report = mod.artifact_dir("sessions", base=Path()) / "session.json"
    return report.relative_to(Path.cwd()).as_posix()


class TestCompleteSessionLog:
    def _make_session_json(self, sessions_dir, name="2026-02-11-session-1.json"):
        """Create a minimal valid session JSON for testing."""
        session = {
            "session": {
                "number": 1,
                "date": "2026-02-11",
                "branch": "feat/test",
                "startingCommit": "abc1234",
                "objective": "Test session",
            },
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"level": "MUST", "Complete": True, "Evidence": "done"},
                },
                "sessionEnd": {
                    "checklistComplete": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "handoffPreserved": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "serenaMemoryUpdated": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "markdownLintRun": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "qaValidation": {
                        "level": "MUST",
                        "Complete": True,
                        "Evidence": "SKIPPED: investigation-only",
                    },
                    "changesCommitted": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "validationPassed": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "tasksUpdated": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                    "retrospectiveInvoked": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                },
            },
            "workLog": [],
            "endingCommit": "",
            "nextSteps": [],
        }
        path = os.path.join(sessions_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        return path

    def test_dry_run_no_changes(self, tmp_path):
        sessions_dir = _sessions_dir(tmp_path)
        os.makedirs(sessions_dir, exist_ok=True)
        session_path = self._make_session_json(sessions_dir)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--git-common-dir"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path / ".git"), stderr="")
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="abc1234", stderr="")
            if cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[0] == "npx":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")

        mod = _load_module()
        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", session_path, "--dry-run"])

        # Dry run should succeed (0) or report todos (1) depending on evidence state
        assert result in (0, 1)

        # Verify file was NOT modified (dry run)
        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["endingCommit"] == ""

    def test_missing_session_file_returns_1(self, tmp_path):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--git-common-dir"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path / ".git"), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", "/nonexistent/file.json"])

        assert result == 1

    def test_invalid_json_returns_1(self, tmp_path):
        sessions_dir = _sessions_dir(tmp_path)
        os.makedirs(sessions_dir, exist_ok=True)
        bad_file = os.path.join(sessions_dir, "bad.json")
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not json")

        mod = _load_module()

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--git-common-dir"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path / ".git"), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", bad_file])

        assert result == 1

    def test_existing_ending_commit_is_preserved_by_default(self):
        mod = _load_module()
        session = {"endingCommit": "old1234"}

        change = mod._set_ending_commit(
            session,
            "new5678",
            refresh=False,
        )

        assert change is None
        assert session["endingCommit"] == "old1234"

    def test_refresh_ending_commit_replaces_stale_value(self):
        mod = _load_module()
        session = {"endingCommit": "old1234"}

        change = mod._set_ending_commit(
            session,
            "new5678",
            refresh=True,
        )

        assert change == "Refreshed endingCommit: new5678"
        assert session["endingCommit"] == "new5678"

    def test_refresh_ending_commit_aligns_episode_comparison(self):
        mod = _load_module()
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

        change = mod._set_ending_commit(
            session,
            full_commit,
            refresh=True,
        )

        assert change == f"Refreshed endingCommit: {'a' * 10}"
        assert session["endingCommit"] == "a" * 10
        assert session["episodeMetrics"]["comparison"]["head"] == full_commit

    def test_refresh_aligns_comparison_when_ending_commit_is_current(self):
        mod = _load_module()
        full_commit = "a" * 40
        session = {
            "endingCommit": "a" * 10,
            "episodeMetrics": {
                "comparison": {
                    "kind": "gitCommitRange",
                    "base": "b" * 40,
                    "head": "c" * 40,
                }
            },
        }

        change = mod._set_ending_commit(
            session,
            full_commit,
            refresh=True,
        )

        assert change == f"Refreshed episode comparison head: {full_commit}"
        assert session["episodeMetrics"]["comparison"]["head"] == full_commit

    def test_refresh_ending_commit_flag_is_opt_in(self):
        mod = _load_module()

        default_args = mod.build_parser().parse_args([])
        refresh_args = mod.build_parser().parse_args(
            ["--refresh-ending-commit"]
        )

        assert default_args.refresh_ending_commit is False
        assert refresh_args.refresh_ending_commit is True

    def test_markdown_files_flag_accepts_explicit_paths(self):
        mod = _load_module()

        args = mod.build_parser().parse_args(
            ["--markdown-files", "one.md", "two.md"]
        )

        assert args.markdown_files == ["one.md", "two.md"]

    def test_markdown_files_flag_rejects_empty_scope(self):
        mod = _load_module()

        with pytest.raises(SystemExit):
            mod.build_parser().parse_args(["--markdown-files"])

    def test_qa_report_flag_accepts_path(self):
        mod = _load_module()

        args = mod.build_parser().parse_args(
            ["--qa-report", "qa/report.md"]
        )

        assert args.qa_report == "qa/report.md"

    def test_qa_report_evidence_accepts_report_under_qa_root(self, tmp_path):
        # ADR-096: validate_qa_report() always runs post_qa_code_changes,
        # which shells out to git. Mock it here since this test exercises
        # _qa_report_evidence's own file-resolution logic, not staleness
        # detection (that is covered separately in tests/test_qa_report.py
        # and tests/test_validate_session_json.py).
        mod = _load_module()
        session_log = _session_log(mod)
        report = mod.artifact_dir("qa", base=tmp_path) / "report.md"
        report.parent.mkdir(parents=True)
        report.write_text(
            "---\n"
            "qaVerdict: PASS\n"
            f"qaSessionLog: {session_log}\n"
            f"qaCommit: {'a' * 40}\n"
            "---\n"
            "# QA\n",
            encoding="utf-8",
        )

        with mock.patch.object(
            sys.modules["qa_report"], "post_qa_code_changes", return_value=[]
        ):
            evidence = mod._qa_report_evidence(
                tmp_path,
                str(report),
                mod.QaBinding(
                    session_log=session_log,
                    commit="a" * 40,
                ),
            )

        assert evidence == report.relative_to(tmp_path).as_posix()

    def test_qa_report_evidence_rejects_deferred_report(self, tmp_path):
        mod = _load_module()
        session_log = _session_log(mod)
        report = mod.artifact_dir("qa", base=tmp_path) / "report.md"
        report.parent.mkdir(parents=True)
        report.write_text(
            "---\n"
            "qaVerdict: DEFERRED\n"
            f"qaSessionLog: {session_log}\n"
            f"qaCommit: {'a' * 40}\n"
            "---\n"
            "# QA\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="verdict must be PASS"):
            mod._qa_report_evidence(
                tmp_path,
                str(report),
                mod.QaBinding(
                    session_log=session_log,
                    commit="a" * 40,
                ),
            )

    def test_qa_report_evidence_rejects_path_outside_qa_root(self, tmp_path):
        mod = _load_module()
        session_log = _session_log(mod)
        report = tmp_path / "report.md"
        report.write_text("# QA\n", encoding="utf-8")

        with pytest.raises(ValueError, match="must be under"):
            mod._qa_report_evidence(
                tmp_path,
                str(report),
                mod.QaBinding(
                    session_log=session_log,
                    commit="a" * 40,
                ),
            )

    def test_qa_report_evidence_rejects_missing_report(self, tmp_path):
        mod = _load_module()
        session_log = _session_log(mod)
        report = mod.artifact_dir("qa", base=tmp_path) / "missing.md"

        with pytest.raises(ValueError, match="not found"):
            mod._qa_report_evidence(
                tmp_path,
                str(report),
                mod.QaBinding(
                    session_log=session_log,
                    commit="a" * 40,
                ),
            )

    def test_required_evidence_rejects_missing_qa_validation(self):
        mod = _load_module()
        session_end = {
            "handoffPreserved": {"level": "MUST", "Complete": True},
            "serenaMemoryUpdated": {"level": "MUST", "Complete": True},
            "markdownLintRun": {"level": "MUST", "Complete": True},
            "changesCommitted": {"level": "MUST", "Complete": True},
            "validationPassed": {"level": "MUST", "Complete": True},
        }

        assert mod._must_items_complete(session_end) is False

    def test_required_evidence_rejects_qa_with_wrong_level(self):
        mod = _load_module()
        session_end = {
            "handoffPreserved": {"level": "MUST", "Complete": True},
            "serenaMemoryUpdated": {"level": "MUST", "Complete": True},
            "markdownLintRun": {"level": "MUST", "Complete": True},
            "qaValidation": {"level": "SHOULD", "Complete": True},
            "changesCommitted": {"level": "MUST", "Complete": True},
            "validationPassed": {"level": "MUST", "Complete": True},
        }

        assert mod._must_items_complete(session_end) is False

    def test_markdown_lint_records_partial_selection(self, tmp_path):
        mod = _load_module()
        pre_pr = tmp_path / "scripts" / "validation" / "pre_pr.py"
        pre_pr.parent.mkdir(parents=True)
        pre_pr.write_text("", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                "[WARNING] Markdown linting checked 1 of 2 target(s); "
                "the rest were excluded"
            ),
            stderr="",
        )

        with (
            mock.patch.object(
                mod,
                "_get_repo_root",
                return_value=str(tmp_path),
            ),
            mock.patch("subprocess.run", return_value=completed),
        ):
            success, evidence = mod._run_markdown_lint(
                ["one.md", "two.md"]
            )

        assert success is True
        assert evidence == (
            "pre_pr.py --markdown-lint-only: 1 of 2 files linted"
        )

    def test_markdown_lint_records_zero_as_not_linted(self, tmp_path):
        mod = _load_module()
        pre_pr = tmp_path / "scripts" / "validation" / "pre_pr.py"
        pre_pr.parent.mkdir(parents=True)
        pre_pr.write_text("", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                "[WARNING] Markdown linting selected 0 of 2 target(s): "
                "nothing was checked"
            ),
            stderr="",
        )

        with (
            mock.patch.object(
                mod,
                "_get_repo_root",
                return_value=str(tmp_path),
            ),
            mock.patch("subprocess.run", return_value=completed),
        ):
            success, evidence = mod._run_markdown_lint(
                ["one.md", "two.md"]
            )

        assert success is False
        assert evidence == (
            "NOT LINTED: pre_pr.py --markdown-lint-only "
            "selected 0 of 2 files"
        )

    def test_uncommitted_changes_ignores_owned_evidence(self):
        mod = _load_module()
        qa_report = (
            mod.artifact_dir("qa", base=Path()) / "report.md"
        ).as_posix()
        session_log = (
            Path(_sessions_dir(Path())) / "session.json"
        ).as_posix()
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                f"A  {qa_report}\0"
                f" M {session_log}\0"
            ),
            stderr="",
        )

        with mock.patch(
            "subprocess.run", return_value=completed
        ) as run:
            dirty = mod._test_uncommitted_changes(
                exclude_paths=[qa_report, session_log]
            )

        assert dirty is False
        run.assert_called_once_with(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )

    def test_uncommitted_changes_keeps_unowned_files(self):
        mod = _load_module()
        qa_report = (
            mod.artifact_dir("qa", base=Path()) / "report.md"
        ).as_posix()
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                f"A  {qa_report}\n"
                " M scripts/validation/memory_index.py\n"
            ),
            stderr="",
        )

        with mock.patch("subprocess.run", return_value=completed):
            dirty = mod._test_uncommitted_changes(
                exclude_paths=[qa_report]
            )

        assert dirty is True

    def test_missing_ending_commit_fails_closed(self, tmp_path):
        sessions_dir = _sessions_dir(tmp_path)
        os.makedirs(sessions_dir, exist_ok=True)
        session_path = self._make_session_json(sessions_dir)
        mod = _load_module()

        with (
            mock.patch.object(
                mod,
                "_get_repo_root",
                return_value=str(tmp_path),
            ),
            mock.patch.object(
                mod,
                "_get_ending_commit",
                return_value=None,
            ),
        ):
            result = mod.main(["--session-path", session_path])

        assert result == 1
