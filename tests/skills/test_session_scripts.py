"""Tests for session skill scripts.

Covers:
- new_session_log_json.py
- complete_session_log.py
- get_validation_errors.py
- convert_session_to_json.py
- test_investigation_eligibility.py
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add session skill script directories to sys.path.
_project_root = Path(__file__).resolve().parents[2]
_session_init = _project_root / ".claude" / "skills" / "session-init" / "scripts"
_session_end = _project_root / ".claude" / "skills" / "session-end" / "scripts"
_log_fixer = _project_root / ".claude" / "skills" / "session-log-fixer" / "scripts"
_migration = _project_root / ".claude" / "skills" / "session-migration" / "scripts"
_qa_eligibility = _project_root / ".claude" / "skills" / "session-qa-eligibility" / "scripts"

for _p in (
    str(_session_init),
    str(_session_end),
    str(_log_fixer),
    str(_migration),
    str(_qa_eligibility),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# new_session_log_json
# ---------------------------------------------------------------------------

class TestNewSessionLogJson:
    """Tests for new_session_log_json module."""

    def _import(self):
        import importlib
        import new_session_log_json as mod
        importlib.reload(mod)
        return mod

    def test_auto_detect_session_number_empty_dir(self, tmp_path):
        mod = self._import()
        result = mod.auto_detect_session_number(tmp_path)
        assert result == 1

    def test_auto_detect_increments(self, tmp_path):
        mod = self._import()
        (tmp_path / "2024-01-01-session-3.json").write_text("{}")
        (tmp_path / "2024-01-01-session-5.json").write_text("{}")
        result = mod.auto_detect_session_number(tmp_path)
        assert result == 6

    def test_auto_detect_nonexistent_dir(self, tmp_path):
        mod = self._import()
        missing = tmp_path / "nonexistent"
        result = mod.auto_detect_session_number(missing)
        assert result == 1

    def test_get_max_existing_none_when_no_files(self, tmp_path):
        mod = self._import()
        assert mod.get_max_existing(tmp_path) is None

    def test_get_max_existing_returns_max(self, tmp_path):
        mod = self._import()
        (tmp_path / "2024-01-01-session-2.json").write_text("{}")
        (tmp_path / "2024-01-01-session-7.json").write_text("{}")
        assert mod.get_max_existing(tmp_path) == 7

    def test_validate_session_ceiling_ok(self, tmp_path):
        mod = self._import()
        (tmp_path / "2024-01-01-session-1.json").write_text("{}")
        # Should not raise or exit - session 5 is within +10 of max 1
        mod.validate_session_ceiling(5, tmp_path)

    def test_validate_session_ceiling_rejects_large_jump(self, tmp_path):
        mod = self._import()
        (tmp_path / "2024-01-01-session-1.json").write_text("{}")
        # max=1, ceiling=11, session 20 should fail
        with pytest.raises(SystemExit) as exc:
            mod.validate_session_ceiling(20, tmp_path)
        assert exc.value.code == 1

    def test_get_git_branch_returns_branch(self):
        mod = self._import()
        proc = make_proc(stdout="my-branch", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.get_git_branch()
        assert result == "my-branch"

    def test_get_git_branch_fallback(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mod.get_git_branch()
        assert result == "unknown"

    def test_get_git_branch_nonzero_returncode(self):
        mod = self._import()
        proc = make_proc(returncode=1)
        with patch("subprocess.run", return_value=proc):
            result = mod.get_git_branch()
        assert result == "unknown"

    def test_get_git_commit_returns_sha(self):
        mod = self._import()
        proc = make_proc(stdout="abc1234", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.get_git_commit()
        assert result == "abc1234"

    def test_get_git_commit_timeout(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
            result = mod.get_git_commit()
        assert result == "unknown"

    def test_build_session_object_structure(self):
        mod = self._import()
        obj = mod.build_session_object(3, "2024-01-01", "feat/test", "abc1234", "test objective")
        assert obj["session"]["number"] == 3
        assert obj["session"]["branch"] == "feat/test"
        assert obj["session"]["startingCommit"] == "abc1234"
        assert obj["session"]["objective"] == "test objective"
        assert "protocolCompliance" in obj
        assert "sessionStart" in obj["protocolCompliance"]
        assert "sessionEnd" in obj["protocolCompliance"]
        assert "workLog" in obj

    def test_build_session_object_empty_objective(self):
        mod = self._import()
        obj = mod.build_session_object(1, "2024-01-01", "main", "abc", "")
        assert "[TODO:" in obj["session"]["objective"]

    def test_build_session_object_main_branch_not_on_main(self):
        mod = self._import()
        obj = mod.build_session_object(1, "2024-01-01", "main", "abc", "test")
        not_on_main = obj["protocolCompliance"]["sessionStart"]["notOnMain"]
        assert not_on_main["Complete"] is False

    def test_build_session_object_feature_branch_on_main(self):
        mod = self._import()
        obj = mod.build_session_object(1, "2024-01-01", "feature/x", "abc", "test")
        not_on_main = obj["protocolCompliance"]["sessionStart"]["notOnMain"]
        assert not_on_main["Complete"] is True

    def test_write_session_file_creates_file(self, tmp_path):
        mod = self._import()
        session_data = {"session": {"number": 1}, "workLog": []}
        file_path = mod.write_session_file(tmp_path, "2024-01-01", 1, session_data)
        assert file_path.exists()
        content = json.loads(file_path.read_text())
        assert content["session"]["number"] == 1

    def test_write_session_file_retries_on_collision(self, tmp_path):
        mod = self._import()
        # Pre-create session 1 to force collision
        (tmp_path / "2024-01-01-session-1.json").write_text("{}")
        session_data = {"session": {"number": 1}, "workLog": []}
        file_path = mod.write_session_file(tmp_path, "2024-01-01", 1, session_data)
        # Should have created session 2
        assert "session-2" in file_path.name

    def test_main_creates_file(self, tmp_path, monkeypatch):
        mod = self._import()
        sessions_dir = tmp_path / ".agents" / "sessions"

        def fake_get_sessions_dir(root):
            return sessions_dir

        def fake_get_repo_root(script_dir):
            return tmp_path

        monkeypatch.setattr(mod, "get_sessions_dir", fake_get_sessions_dir)
        monkeypatch.setattr(mod, "get_repo_root", fake_get_repo_root)

        with (
            patch("subprocess.run", return_value=make_proc(stdout="test-branch")),
        ):
            sys.argv = ["new_session_log_json.py", "--session-number", "1", "--objective", "test"]
            mod.main()

        created = list(sessions_dir.glob("*.json"))
        assert len(created) == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["new_session_log_json.py", "--help"]
            import new_session_log_json as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# complete_session_log
# ---------------------------------------------------------------------------

class TestCompleteSessionLog:
    """Tests for complete_session_log module."""

    def _import(self):
        import importlib
        import complete_session_log as mod
        importlib.reload(mod)
        return mod

    def _make_session(self):
        return {
            "session": {"number": 1, "date": "2024-01-01", "branch": "main"},
            "protocolCompliance": {
                "sessionEnd": {
                    "checklistComplete": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "handoffNotUpdated": {"level": "MUST NOT", "Complete": False, "Evidence": ""},
                    "serenaMemoryUpdated": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "markdownLintRun": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "changesCommitted": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "validationPassed": {"level": "MUST", "Complete": False, "Evidence": ""},
                },
            },
            "workLog": [],
            "endingCommit": "",
        }

    def test_find_current_session_log_today(self, tmp_path):
        mod = self._import()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        f = tmp_path / f"{today}-session-1.json"
        f.write_text(json.dumps(self._make_session()))
        result = mod.find_current_session_log(tmp_path)
        assert result == f

    def test_find_current_session_log_none(self, tmp_path):
        mod = self._import()
        result = mod.find_current_session_log(tmp_path)
        assert result is None

    def test_find_current_session_log_latest_fallback(self, tmp_path):
        mod = self._import()
        # Create an old file
        old = tmp_path / "2023-01-01-session-1.json"
        old.write_text(json.dumps(self._make_session()))
        result = mod.find_current_session_log(tmp_path)
        assert result == old

    def test_get_ending_commit_success(self):
        mod = self._import()
        proc = make_proc(stdout="abc1234", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.get_ending_commit()
        assert result == "abc1234"

    def test_get_ending_commit_none_on_failure(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mod.get_ending_commit()
        assert result is None

    def test_test_handoff_modified_false(self):
        mod = self._import()
        proc = make_proc(stdout="src/main.py\nREADME.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_handoff_modified()
        assert result is False

    def test_test_handoff_modified_true(self):
        mod = self._import()
        proc = make_proc(stdout=".agents/HANDOFF.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_handoff_modified()
        assert result is True

    def test_test_serena_memory_updated_true(self):
        mod = self._import()
        proc = make_proc(stdout=".serena/memories/test.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_serena_memory_updated()
        assert result is True

    def test_test_serena_memory_updated_false(self):
        mod = self._import()
        proc = make_proc(stdout="src/main.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_serena_memory_updated()
        assert result is False

    def test_test_uncommitted_changes_clean(self):
        mod = self._import()
        proc = make_proc(stdout="", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_uncommitted_changes()
        assert result is False

    def test_test_uncommitted_changes_dirty(self):
        mod = self._import()
        proc = make_proc(stdout=" M file.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.test_uncommitted_changes()
        assert result is True

    def test_run_markdown_lint_no_files(self):
        mod = self._import()
        proc = make_proc(stdout="", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.run_markdown_lint()
        assert result["Success"] is True
        assert "No markdown files" in result["Output"]

    def test_run_markdown_lint_with_files_success(self):
        mod = self._import()
        procs = [
            make_proc(stdout="README.md", returncode=0),  # staged diff
            make_proc(stdout="", returncode=0),            # unstaged diff
            make_proc(returncode=0),                       # markdownlint
        ]
        with patch("subprocess.run", side_effect=procs):
            result = mod.run_markdown_lint()
        assert result["Success"] is True

    def test_validate_path_containment_inside(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "session-1.json"
        session_file.write_text("{}")
        assert mod.validate_path_containment(session_file, sessions_dir) is True

    def test_validate_path_containment_outside(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}")
        assert mod.validate_path_containment(outside, sessions_dir) is False

    def test_main_session_path_not_found(self, tmp_path):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            sys.argv = [
                "complete_session_log.py",
                "--session-path", str(tmp_path / "missing.json"),
            ]
            mod.main()
        assert exc.value.code == 1

    def test_main_no_session_logs_exits_1(self, tmp_path, monkeypatch):
        import importlib
        import complete_session_log as mod
        importlib.reload(mod)

        def fake_root(script_dir):
            return tmp_path

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "get_repo_root", fake_root)

        sys.argv = ["complete_session_log.py"]
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["complete_session_log.py", "--help"]
            import complete_session_log as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# get_validation_errors
# ---------------------------------------------------------------------------

class TestGetValidationErrors:
    """Tests for get_validation_errors module."""

    def _import(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        return mod

    def test_parse_job_summary_overall_verdict(self):
        mod = self._import()
        summary = "Overall Verdict: **NON_COMPLIANT**\n"
        result = mod.parse_job_summary(summary)
        assert result["OverallVerdict"] == "NON_COMPLIANT"

    def test_parse_job_summary_must_failure_count(self):
        mod = self._import()
        summary = "3 MUST requirement(s) not met\n"
        result = mod.parse_job_summary(summary)
        assert result["MustFailureCount"] == 3

    def test_parse_job_summary_non_compliant_sessions(self):
        mod = self._import()
        summary = (
            "| Session File | Status | Failures |\n"
            "| `2024-01-01-session-1.json` | NON_COMPLIANT | 2 |\n"
        )
        result = mod.parse_job_summary(summary)
        assert len(result["NonCompliantSessions"]) == 1
        assert result["NonCompliantSessions"][0]["File"] == "2024-01-01-session-1.json"
        assert result["NonCompliantSessions"][0]["MustFailures"] == 2

    def test_parse_job_summary_empty(self):
        mod = self._import()
        result = mod.parse_job_summary("")
        assert result["OverallVerdict"] is None
        assert result["MustFailureCount"] == 0
        assert result["NonCompliantSessions"] == []

    def test_run_gh_success(self):
        mod = self._import()
        proc = make_proc(stdout="result output", returncode=0)
        with patch("subprocess.run", return_value=proc):
            output = mod.run_gh(["some", "args"])
        assert output == "result output"

    def test_run_gh_failure_raises(self):
        mod = self._import()
        proc = make_proc(stderr="error", returncode=1)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(RuntimeError, match="gh command failed"):
                mod.run_gh(["bad", "args"])

    def test_get_run_id_from_pr_happy_path(self):
        mod = self._import()
        pr_info = json.dumps({"headRefName": "feat/test"})
        runs = json.dumps([
            {"databaseId": 100, "conclusion": "success"},
            {"databaseId": 200, "conclusion": "failure"},
        ])
        with patch.object(mod, "run_gh", side_effect=[pr_info, runs]):
            run_id = mod.get_run_id_from_pr(10)
        assert run_id == "200"

    def test_get_run_id_from_pr_no_failure(self):
        mod = self._import()
        pr_info = json.dumps({"headRefName": "feat/test"})
        runs = json.dumps([{"databaseId": 100, "conclusion": "success"}])
        with patch.object(mod, "run_gh", side_effect=[pr_info, runs]):
            with pytest.raises(RuntimeError):
                mod.get_run_id_from_pr(10)

    def test_main_run_id_no_errors_exits_2(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        jobs = json.dumps({
            "jobs": [{"name": "Aggregate Results", "id": 1}]
        })
        log = "no relevant content"
        with patch.object(mod, "run_gh", side_effect=[jobs, log]):
            sys.argv = ["get_validation_errors.py", "--run-id", "12345"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 2

    def test_main_no_aggregate_job_exits_1(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        jobs = json.dumps({"jobs": [{"name": "Other Job", "id": 1}]})
        with patch.object(mod, "run_gh", side_effect=[jobs]):
            sys.argv = ["get_validation_errors.py", "--run-id", "999"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["get_validation_errors.py", "--help"]
            import get_validation_errors as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# convert_session_to_json
# ---------------------------------------------------------------------------

class TestConvertSessionToJson:
    """Tests for convert_session_to_json module."""

    def _import(self):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        return mod

    def _make_md(self):
        return """# Session Log

**Branch**: feat/test-branch
**Commit**: `abc1234`

## Objective

Implement the new feature

## Work Log

### Task 1

Did some important work here that spans multiple lines and describes the task in detail.
"""

    def test_convert_basic_fields(self):
        mod = self._import()
        content = self._make_md()
        result = mod.convert_from_markdown(content, "2024-01-15-session-3.md")
        assert result["session"]["number"] == 3
        assert result["session"]["date"] == "2024-01-15"
        assert result["session"]["branch"] == "feat/test-branch"
        assert result["session"]["startingCommit"] == "abc1234"
        assert "Implement" in result["session"]["objective"]

    def test_convert_no_session_number(self):
        mod = self._import()
        result = mod.convert_from_markdown("", "session.md")
        assert result["session"]["number"] == 0

    def test_convert_no_date(self):
        mod = self._import()
        result = mod.convert_from_markdown("", "session-1.md")
        assert result["session"]["date"] == ""

    def test_convert_fallback_objective(self):
        mod = self._import()
        result = mod.convert_from_markdown("", "2024-01-01-session-1.md")
        assert "[Migrated" in result["session"]["objective"]

    def test_find_checklist_item_found(self):
        mod = self._import()
        content = "| something | activate_project | [x] | evidence here |"
        result = mod.find_checklist_item(content, "activate_project")
        assert result["Complete"] is True
        assert result["Evidence"] == "evidence here"

    def test_find_checklist_item_not_found(self):
        mod = self._import()
        result = mod.find_checklist_item("no match here", "activate_project")
        assert result["Complete"] is False

    def test_parse_work_log_extracts_entries(self):
        mod = self._import()
        content = """## Work Log

### Task A

Completed the important implementation work with detailed steps and explanation.

### Task B

Reviewed and approved the PR changes with extensive documentation.
"""
        entries = mod.parse_work_log(content)
        assert len(entries) >= 1
        titles = [e["action"] for e in entries]
        assert any("Task A" in t for t in titles)

    def test_parse_work_log_empty(self):
        mod = self._import()
        entries = mod.parse_work_log("# No work log section")
        assert entries == []

    def test_main_path_not_found_exits_1(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        sys.argv = [
            "convert_session_to_json.py",
            str(tmp_path / "missing_path"),
        ]
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 1

    def test_main_single_file(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        sys.argv = ["convert_session_to_json.py", str(md_file)]
        mod.main()
        json_file = tmp_path / "2024-01-01-session-1.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "session" in data

    def test_main_dry_run_no_file_created(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        sys.argv = [
            "convert_session_to_json.py",
            str(md_file),
            "--dry-run",
        ]
        mod.main()
        json_file = tmp_path / "2024-01-01-session-1.json"
        assert not json_file.exists()

    def test_main_skips_existing_without_force(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        json_file = tmp_path / "2024-01-01-session-1.json"
        json_file.write_text('{"existing": true}')
        sys.argv = ["convert_session_to_json.py", str(md_file)]
        mod.main()
        # Should still contain original content (was skipped)
        data = json.loads(json_file.read_text())
        assert data.get("existing") is True

    def test_main_force_overwrites(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        json_file = tmp_path / "2024-01-01-session-1.json"
        json_file.write_text('{"existing": true}')
        sys.argv = [
            "convert_session_to_json.py",
            str(md_file),
            "--force",
        ]
        mod.main()
        data = json.loads(json_file.read_text())
        assert "session" in data

    def test_main_directory_converts_all_sessions(self, tmp_path):
        import importlib
        import convert_session_to_json as mod
        importlib.reload(mod)
        for i in range(1, 4):
            f = tmp_path / f"2024-01-0{i}-session-{i}.md"
            f.write_text(self._make_md())
        # Also add a non-session file that should be ignored
        (tmp_path / "notes.md").write_text("some notes")
        sys.argv = ["convert_session_to_json.py", str(tmp_path)]
        mod.main()
        jsons = list(tmp_path.glob("*-session-*.json"))
        assert len(jsons) == 3

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["convert_session_to_json.py", "--help"]
            import convert_session_to_json as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# test_investigation_eligibility
# ---------------------------------------------------------------------------

class TestInvestigationEligibility:
    """Tests for test_investigation_eligibility module."""

    def _import(self):
        import importlib
        import test_investigation_eligibility as mod
        importlib.reload(mod)
        return mod

    def test_file_matches_sessions_dir(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".agents/sessions/2024-01-01-session-1.json") is True

    def test_file_matches_analysis_dir(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".agents/analysis/report.md") is True

    def test_file_matches_serena_memories(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".serena/memories/my-note.md") is True

    def test_file_matches_retrospective(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".agents/retrospective/retro.md") is True

    def test_file_matches_adr_review(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".agents/architecture/REVIEW-001.md") is True

    def test_file_does_not_match_src(self):
        mod = self._import()
        assert mod.file_matches_allowlist("src/main.py") is False

    def test_file_does_not_match_github_workflow(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".github/workflows/ci.yml") is False

    def test_file_does_not_match_scripts(self):
        mod = self._import()
        assert mod.file_matches_allowlist("scripts/deploy.py") is False

    def test_windows_path_normalized(self):
        mod = self._import()
        assert mod.file_matches_allowlist(".agents\\sessions\\test.json") is True

    def test_get_staged_files_success(self):
        mod = self._import()
        proc = make_proc(stdout=".agents/sessions/test.json\nother.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            files, ok = mod.get_staged_files()
        assert ok is True
        assert ".agents/sessions/test.json" in files

    def test_get_staged_files_git_failure(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            files, ok = mod.get_staged_files()
        assert ok is False
        assert files == []

    def test_get_staged_files_empty_output(self):
        mod = self._import()
        proc = make_proc(stdout="", returncode=0)
        with patch("subprocess.run", return_value=proc):
            files, ok = mod.get_staged_files()
        assert ok is True
        assert files == []

    def test_main_eligible(self, capsys):
        import importlib
        import test_investigation_eligibility as mod
        importlib.reload(mod)
        proc = make_proc(stdout=".agents/sessions/test.json", returncode=0)
        with patch("subprocess.run", return_value=proc):
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Eligible"] is True
        assert parsed["Violations"] == []

    def test_main_not_eligible(self, capsys):
        import importlib
        import test_investigation_eligibility as mod
        importlib.reload(mod)
        proc = make_proc(stdout=".agents/sessions/test.json\nsrc/main.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Eligible"] is False
        assert "src/main.py" in parsed["Violations"]

    def test_main_git_error_returns_eligible_false(self, capsys):
        import importlib
        import test_investigation_eligibility as mod
        importlib.reload(mod)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Eligible"] is False
        assert "Error" in parsed

    def test_main_always_exits_0(self):
        import importlib
        import test_investigation_eligibility as mod
        importlib.reload(mod)
        proc = make_proc(stdout="src/main.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            # Should not raise SystemExit with non-zero code
            try:
                mod.main()
            except SystemExit as e:
                assert e.code == 0
