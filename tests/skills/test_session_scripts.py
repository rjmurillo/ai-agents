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
    """Tests for new_session_log_json module.

    The source script exposes: build_parser, main, _get_branch, _get_commit,
    _get_repo_root. All session-building logic is inlined in main().
    """

    def _import(self):
        import importlib
        import new_session_log_json as mod
        importlib.reload(mod)
        return mod

    def test_get_branch_returns_branch(self):
        mod = self._import()
        proc = make_proc(stdout="my-branch", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_branch()
        assert result == "my-branch"

    def test_get_branch_fallback(self):
        mod = self._import()
        proc = make_proc(returncode=1)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_branch()
        assert result == "unknown"

    def test_get_commit_returns_sha(self):
        mod = self._import()
        proc = make_proc(stdout="abc1234", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_commit()
        assert result == "abc1234"

    def test_get_commit_fallback(self):
        mod = self._import()
        proc = make_proc(returncode=1)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_commit()
        assert result == "unknown"

    def test_main_creates_file(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / ".agents" / "sessions"

        proc = make_proc(stdout="test-branch", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            sys.argv = ["new_session_log_json.py", "--session-number", "1", "--objective", "test"]
            rc = mod.main()

        assert rc == 0
        created = list(sessions_dir.glob("*.json"))
        assert len(created) == 1

    def test_main_auto_detects_session_number(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "2024-01-01-session-3.json").write_text("{}")

        proc = make_proc(stdout="test-branch", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--objective", "test"])

        assert rc == 0
        created = list(sessions_dir.glob("*-session-4.json"))
        assert len(created) == 1

    def test_main_rejects_large_session_jump(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "2024-01-01-session-1.json").write_text("{}")

        proc = make_proc(stdout="test-branch", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "20", "--objective", "test"])

        assert rc == 1

    def test_main_retries_on_collision(self, tmp_path):
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        # Pre-create session 1 with today's date to force collision
        (sessions_dir / f"{today}-session-1.json").write_text("{}")

        proc = make_proc(stdout="test-branch", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "1", "--objective", "test"])

        assert rc == 0
        # Should have created session 2
        created = list(sessions_dir.glob(f"{today}-session-2.json"))
        assert len(created) == 1

    def test_main_session_structure(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / ".agents" / "sessions"

        proc = make_proc(stdout="feat/test", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "3", "--objective", "test objective"])

        assert rc == 0
        created = list(sessions_dir.glob("*.json"))
        assert len(created) == 1
        obj = json.loads(created[0].read_text())
        assert obj["session"]["number"] == 3
        assert obj["session"]["objective"] == "test objective"
        assert "protocolCompliance" in obj
        assert "sessionStart" in obj["protocolCompliance"]
        assert "sessionEnd" in obj["protocolCompliance"]
        assert "workLog" in obj

    def test_main_empty_objective_gets_todo(self, tmp_path):
        mod = self._import()

        proc = make_proc(stdout="main", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "1"])

        assert rc == 0
        sessions_dir = tmp_path / ".agents" / "sessions"
        created = list(sessions_dir.glob("*.json"))
        obj = json.loads(created[0].read_text())
        assert "[TODO:" in obj["session"]["objective"]

    def test_main_branch_not_on_main(self, tmp_path):
        mod = self._import()

        proc = make_proc(stdout="feature/x", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "1", "--objective", "test"])

        assert rc == 0
        sessions_dir = tmp_path / ".agents" / "sessions"
        created = list(sessions_dir.glob("*.json"))
        obj = json.loads(created[0].read_text())
        not_on_main = obj["protocolCompliance"]["sessionStart"]["notOnMain"]
        assert not_on_main["Complete"] is True

    def test_main_branch_on_main(self, tmp_path):
        mod = self._import()

        proc = make_proc(stdout="main", returncode=0)
        with patch("subprocess.run", return_value=proc), \
             patch.object(mod, "_get_repo_root", return_value=str(tmp_path)):
            rc = mod.main(["--session-number", "1", "--objective", "test"])

        assert rc == 0
        sessions_dir = tmp_path / ".agents" / "sessions"
        created = list(sessions_dir.glob("*.json"))
        obj = json.loads(created[0].read_text())
        not_on_main = obj["protocolCompliance"]["sessionStart"]["notOnMain"]
        assert not_on_main["Complete"] is False

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
    """Tests for complete_session_log module.

    Functions are prefixed with underscore (private). Return types differ
    from the original public API:
    - _run_markdown_lint returns (bool, str) not dict
    - _validate_path_containment returns str|None not bool
    - _test_handoff_modified checks both staged and unstaged diffs
    """

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
                    "handoffPreserved": {"level": "MUST", "Complete": False, "Evidence": ""},
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
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        f = tmp_path / f"{today}-session-1.json"
        f.write_text(json.dumps(self._make_session()))
        result = mod._find_current_session_log(str(tmp_path))
        assert result == str(f)

    def test_find_current_session_log_none(self, tmp_path):
        mod = self._import()
        result = mod._find_current_session_log(str(tmp_path))
        assert result is None

    def test_find_current_session_log_latest_fallback(self, tmp_path):
        mod = self._import()
        # Create an old file
        old = tmp_path / "2023-01-01-session-1.json"
        old.write_text(json.dumps(self._make_session()))
        result = mod._find_current_session_log(str(tmp_path))
        assert result == str(old)

    def test_get_ending_commit_success(self):
        mod = self._import()
        proc = make_proc(stdout="abc1234", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_ending_commit()
        assert result == "abc1234"

    def test_get_ending_commit_none_on_failure(self):
        mod = self._import()
        proc = make_proc(returncode=1)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_ending_commit()
        assert result is None

    def test_test_handoff_modified_false(self):
        mod = self._import()
        proc = make_proc(stdout="src/main.py\nREADME.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_handoff_modified()
        assert result is False

    def test_test_handoff_modified_true(self):
        mod = self._import()
        proc = make_proc(stdout=".agents/HANDOFF.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_handoff_modified()
        assert result is True

    def test_test_serena_memory_updated_true(self):
        mod = self._import()
        proc = make_proc(stdout=".serena/memories/test.md", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_serena_memory_updated()
        assert result is True

    def test_test_serena_memory_updated_false(self):
        mod = self._import()
        proc = make_proc(stdout="src/main.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_serena_memory_updated()
        assert result is False

    def test_test_uncommitted_changes_clean(self):
        mod = self._import()
        proc = make_proc(stdout="", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_uncommitted_changes()
        assert result is False

    def test_test_uncommitted_changes_dirty(self):
        mod = self._import()
        proc = make_proc(stdout=" M file.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._test_uncommitted_changes()
        assert result is True

    def test_run_markdown_lint_no_files(self):
        mod = self._import()
        # Both staged and unstaged return empty
        procs = [
            make_proc(stdout="", returncode=0),  # staged
            make_proc(stdout="", returncode=0),  # unstaged
        ]
        with patch("subprocess.run", side_effect=procs):
            success, output = mod._run_markdown_lint()
        assert success is True
        assert "No markdown files" in output

    def test_run_markdown_lint_with_files_success(self):
        mod = self._import()
        procs = [
            make_proc(stdout="README.md", returncode=0),  # staged diff
            make_proc(stdout="", returncode=0),            # unstaged diff
            make_proc(returncode=0),                       # markdownlint
        ]
        with patch("subprocess.run", side_effect=procs):
            success, output = mod._run_markdown_lint()
        assert success is True

    def test_validate_path_containment_inside(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "session-1.json"
        session_file.write_text("{}")
        result = mod._validate_path_containment(str(session_file), str(sessions_dir))
        assert result is not None  # returns resolved path string

    def test_validate_path_containment_outside(self, tmp_path):
        mod = self._import()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}")
        result = mod._validate_path_containment(str(outside), str(sessions_dir))
        assert result is None

    def test_main_session_path_not_found(self, tmp_path):
        mod = self._import()
        rc = mod.main([
            "--session-path", str(tmp_path / "missing.json"),
        ])
        assert rc == 1

    def test_main_no_session_logs_exits_1(self, tmp_path, monkeypatch):
        import importlib
        import complete_session_log as mod
        importlib.reload(mod)

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "_get_repo_root", lambda: str(tmp_path))

        rc = mod.main([])
        assert rc == 1

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
    """Tests for get_validation_errors module.

    Functions were renamed to private:
    - parse_job_summary -> _parse_job_summary (keys now snake_case)
    - run_gh removed (subprocess.run used directly)
    - get_run_id_from_pr -> _get_run_id_from_pr
    """

    def _import(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        return mod

    def test_parse_job_summary_overall_verdict(self):
        mod = self._import()
        summary = "Overall Verdict: **NON_COMPLIANT**\n"
        result = mod._parse_job_summary(summary)
        assert result["overall_verdict"] == "NON_COMPLIANT"

    def test_parse_job_summary_must_failure_count(self):
        mod = self._import()
        summary = "3 MUST requirement(s) not met\n"
        result = mod._parse_job_summary(summary)
        assert result["must_failure_count"] == 3

    def test_parse_job_summary_non_compliant_sessions(self):
        mod = self._import()
        summary = (
            "| Session File | Status | Failures |\n"
            "| `2024-01-01-session-1.json` | NON_COMPLIANT | 2 |\n"
        )
        result = mod._parse_job_summary(summary)
        assert len(result["non_compliant_sessions"]) == 1
        assert result["non_compliant_sessions"][0]["file"] == "2024-01-01-session-1.json"
        assert result["non_compliant_sessions"][0]["must_failures"] == 2

    def test_parse_job_summary_empty(self):
        mod = self._import()
        result = mod._parse_job_summary("")
        assert result["overall_verdict"] is None
        assert result["must_failure_count"] == 0
        assert result["non_compliant_sessions"] == []

    def test_get_run_id_from_pr_happy_path(self):
        mod = self._import()
        pr_proc = make_proc(
            stdout=json.dumps({"headRefName": "feat/test"}), returncode=0,
        )
        runs_proc = make_proc(
            stdout=json.dumps([
                {"databaseId": 100, "conclusion": "success"},
                {"databaseId": 200, "conclusion": "failure"},
            ]),
            returncode=0,
        )
        with patch("subprocess.run", side_effect=[pr_proc, runs_proc]):
            run_id = mod._get_run_id_from_pr(10)
        assert run_id == "200"

    def test_get_run_id_from_pr_no_failure(self):
        mod = self._import()
        pr_proc = make_proc(
            stdout=json.dumps({"headRefName": "feat/test"}), returncode=0,
        )
        runs_proc = make_proc(
            stdout=json.dumps([{"databaseId": 100, "conclusion": "success"}]),
            returncode=0,
        )
        with patch("subprocess.run", side_effect=[pr_proc, runs_proc]):
            with pytest.raises(RuntimeError):
                mod._get_run_id_from_pr(10)

    def test_main_run_id_no_errors_exits_2(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        # Mock the subprocess.run call that fetches log
        log_proc = make_proc(stdout="no relevant content", returncode=0)
        with patch("subprocess.run", return_value=log_proc):
            rc = mod.main(["--run-id", "12345"])
        assert rc == 2

    def test_main_run_fetch_failure_exits_1(self):
        import importlib
        import get_validation_errors as mod
        importlib.reload(mod)
        log_proc = make_proc(returncode=1, stderr="error")
        with patch("subprocess.run", return_value=log_proc):
            rc = mod.main(["--run-id", "999"])
        assert rc == 1

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
    """Tests for convert_session_to_json module.

    Functions renamed to private:
    - convert_from_markdown -> _convert_markdown_session
    - find_checklist_item -> _find_checklist_item
    - parse_work_log -> _parse_work_log
    """

    def _import(self):
        import importlib.util

        # Load explicitly from the skill path to avoid picking up the
        # scripts/ PowerShell wrapper when pytest-cov reorders imports.
        skill_path = _migration / "convert_session_to_json.py"
        spec = importlib.util.spec_from_file_location(
            "convert_session_to_json", skill_path
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["convert_session_to_json"] = mod
        spec.loader.exec_module(mod)
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
        result = mod._convert_markdown_session(content, "2024-01-15-session-3.md")
        assert result["session"]["number"] == 3
        assert result["session"]["date"] == "2024-01-15"
        assert result["session"]["branch"] == "feat/test-branch"
        assert result["session"]["startingCommit"] == "abc1234"
        assert "Implement" in result["session"]["objective"]

    def test_convert_no_session_number(self):
        mod = self._import()
        result = mod._convert_markdown_session("", "session.md")
        assert result["session"]["number"] == 0

    def test_convert_no_date(self):
        mod = self._import()
        result = mod._convert_markdown_session("", "session-1.md")
        assert result["session"]["date"] == ""

    def test_convert_fallback_objective(self):
        mod = self._import()
        result = mod._convert_markdown_session("", "2024-01-01-session-1.md")
        assert "[Migrated" in result["session"]["objective"]

    def test_find_checklist_item_found(self):
        mod = self._import()
        # AST parser requires a proper markdown table with header and separator
        content = (
            "| Step | Check | Status | Evidence |\n"
            "| --- | --- | --- | --- |\n"
            "| something | activate_project | [x] | evidence here |\n"
        )
        result = mod._find_checklist_item(content, "activate_project")
        assert result["Complete"] is True
        assert result["Evidence"] == "evidence here"

    def test_find_checklist_item_not_found(self):
        mod = self._import()
        result = mod._find_checklist_item("no match here", "activate_project")
        assert result["Complete"] is False

    def test_parse_work_log_extracts_entries(self):
        mod = self._import()
        content = """## Work Log

### Task A

Completed the important implementation work with detailed steps and explanation.

### Task B

Reviewed and approved the PR changes with extensive documentation.
"""
        entries = mod._parse_work_log(content)
        assert len(entries) >= 1
        titles = [e["action"] for e in entries]
        assert any("Task A" in t for t in titles)

    def test_parse_work_log_empty(self):
        mod = self._import()
        entries = mod._parse_work_log("# No work log section")
        assert entries == []

    def test_main_path_not_found_exits_1(self, tmp_path):
        mod = self._import()
        rc = mod.main([str(tmp_path / "missing_path")])
        assert rc == 1

    def test_main_single_file(self, tmp_path):
        mod = self._import()
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        rc = mod.main([str(md_file)])
        assert rc == 0
        json_file = tmp_path / "2024-01-01-session-1.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "session" in data

    def test_main_dry_run_no_file_created(self, tmp_path):
        mod = self._import()
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        rc = mod.main([str(md_file), "--dry-run"])
        assert rc == 0
        json_file = tmp_path / "2024-01-01-session-1.json"
        assert not json_file.exists()

    def test_main_skips_existing_without_force(self, tmp_path):
        mod = self._import()
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        json_file = tmp_path / "2024-01-01-session-1.json"
        json_file.write_text('{"existing": true}')
        rc = mod.main([str(md_file)])
        assert rc == 0
        # Should still contain original content (was skipped)
        data = json.loads(json_file.read_text())
        assert data.get("existing") is True

    def test_main_force_overwrites(self, tmp_path):
        mod = self._import()
        md_file = tmp_path / "2024-01-01-session-1.md"
        md_file.write_text(self._make_md())
        json_file = tmp_path / "2024-01-01-session-1.json"
        json_file.write_text('{"existing": true}')
        rc = mod.main([str(md_file), "--force"])
        assert rc == 0
        data = json.loads(json_file.read_text())
        assert "session" in data

    def test_main_directory_converts_all_sessions(self, tmp_path):
        mod = self._import()
        for i in range(1, 4):
            f = tmp_path / f"2024-01-0{i}-session-{i}.md"
            f.write_text(self._make_md())
        # Also add a non-session file that should be ignored
        (tmp_path / "notes.md").write_text("some notes")
        rc = mod.main([str(tmp_path)])
        assert rc == 0
        jsons = list(tmp_path.glob("*-session-*.json"))
        assert len(jsons) == 3

    def test_help_does_not_crash(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["convert_session_to_json.py", "--help"]
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
