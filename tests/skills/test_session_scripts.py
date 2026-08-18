"""Tests for session skill scripts.

Covers:
- new_session_log_json.py
- complete_session_log.py

The session skill's test_investigation_eligibility.py is covered by its
co-located suite at .claude/skills/session/tests/test_session_eligibility.py.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add session skill script directories to sys.path.
_project_root = Path(__file__).resolve().parents[2]
_session_init = _project_root / ".claude" / "skills" / "session-init" / "scripts"
_session_end = _project_root / ".claude" / "skills" / "session-end" / "scripts"

for _p in (
    str(_session_init),
    str(_session_end),
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
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
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
        # _make_session sets session.branch="main"; mock branch to match.
        with patch.object(mod, "_get_current_branch", return_value="main"):
            result = mod._find_current_session_log(str(tmp_path))
        assert result == str(f)

    def test_find_current_session_log_none(self, tmp_path):
        mod = self._import()
        result = mod._find_current_session_log(str(tmp_path))
        assert result is None

    def test_find_current_session_log_latest_fallback(self, tmp_path):
        mod = self._import()
        # An old session log with a matching branch is still selected.
        old = tmp_path / "2023-01-01-session-1.json"
        old.write_text(json.dumps(self._make_session()))
        with patch.object(mod, "_get_current_branch", return_value="main"):
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
        with patch.object(mod, "_changed_markdown_files", return_value=set()):
            success, output = mod._run_markdown_lint()

        assert success is True
        assert output == "NOT LINTED: no changed markdown files"

    def test_run_markdown_lint_with_files_success(self, tmp_path):
        mod = self._import()
        pre_pr = tmp_path / "scripts" / "validation" / "pre_pr.py"
        pre_pr.parent.mkdir(parents=True)
        pre_pr.write_text("", encoding="utf-8")
        lint_result = make_proc(
            stdout="[INFO] Markdown linting checked 1 of 1 target(s)",
        )

        with (
            patch.object(mod, "_changed_markdown_files", return_value={"README.md"}),
            patch.object(mod, "_get_repo_root", return_value=str(tmp_path)),
            patch("subprocess.run", return_value=lint_result),
        ):
            success, output = mod._run_markdown_lint()

        assert success is True
        assert output == "pre_pr.py --markdown-lint-only: 1 of 1 files linted"

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
# complete_session_log branch-aware selection (issue #4161)
# ---------------------------------------------------------------------------

class TestCompleteSessionLogBranchAware:
    """_find_current_session_log selects by branch field before falling back to mtime."""

    def _import(self):
        import importlib

        import complete_session_log as mod
        importlib.reload(mod)
        return mod

    def _make_session(self, branch: str = "main") -> dict:
        return {
            "session": {"number": 1, "date": "2024-01-01", "branch": branch},
            "workLog": [],
            "endingCommit": "",
        }

    def test_branch_match_wins_over_mtime(self, tmp_path):
        """Returns the log whose branch field matches current branch, not the mtime winner."""
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        import os

        # Older log for our branch
        mine = tmp_path / f"{today}-session-1.json"
        mine.write_text(json.dumps(self._make_session("feature/x")))
        os.utime(mine, (1_000_000_000.0, 1_000_000_000.0))

        # Newer log for another branch (has mtime 2^31 in the future from epoch, still today)
        other = tmp_path / f"{today}-session-2.json"
        other.write_text(json.dumps(self._make_session("feature/other")))
        os.utime(other, (2_000_000_000.0, 2_000_000_000.0))

        with patch.object(mod, "_get_current_branch", return_value="feature/x"):
            result = mod._find_current_session_log(str(tmp_path))

        assert result == str(mine), (
            f"Expected branch-matching log {mine.name}, got {result}"
        )

    def test_newest_branch_match_wins_when_branch_has_multiple_logs(self, tmp_path):
        """Returns the newest matching branch log, not the first filename."""
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        import os

        older = tmp_path / f"{today}-session-1.json"
        older.write_text(json.dumps(self._make_session("feature/x")))
        os.utime(older, (1_000_000_000.0, 1_000_000_000.0))

        newer = tmp_path / f"{today}-session-2.json"
        newer.write_text(json.dumps(self._make_session("feature/x")))
        os.utime(newer, (2_000_000_000.0, 2_000_000_000.0))

        with patch.object(mod, "_get_current_branch", return_value="feature/x"):
            result = mod._find_current_session_log(str(tmp_path))

        assert result == str(newer), (
            f"Expected newest branch-matching log {newer.name}, got {result}"
        )

    def test_fallback_to_mtime_when_no_branch_log(self, tmp_path):
        """Returns None when no log matches the current branch (no mtime fallback)."""
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        import os

        log_old = tmp_path / f"{today}-session-1.json"
        log_old.write_text(json.dumps(self._make_session("feature/other-a")))
        os.utime(log_old, (1_000_000_000.0, 1_000_000_000.0))

        log_new = tmp_path / f"{today}-session-2.json"
        log_new.write_text(json.dumps(self._make_session("feature/other-b")))
        os.utime(log_new, (2_000_000_000.0, 2_000_000_000.0))

        with patch.object(mod, "_get_current_branch", return_value="feature/no-log"):
            result = mod._find_current_session_log(str(tmp_path))

        assert result is None, "Should return None when no log matches the current branch"

    def test_fallback_to_mtime_when_branch_unavailable(self, tmp_path):
        """Returns None when _get_current_branch returns None (no mtime fallback)."""
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        log = tmp_path / f"{today}-session-1.json"
        log.write_text(json.dumps(self._make_session("feature/x")))

        with patch.object(mod, "_get_current_branch", return_value=None):
            result = mod._find_current_session_log(str(tmp_path))

        assert result is None

    def test_legacy_top_level_branch_field_is_matched(self, tmp_path):
        """A log with top-level 'branch' (legacy schema) is also matched by branch."""
        mod = self._import()
        from datetime import UTC, datetime
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        legacy_log = tmp_path / f"{today}-session-1.json"
        legacy_log.write_text(json.dumps({"branch": "feature/legacy"}))

        with patch.object(mod, "_get_current_branch", return_value="feature/legacy"):
            result = mod._find_current_session_log(str(tmp_path))

        assert result == str(legacy_log), "Legacy top-level branch field should be matched"

    def test_get_current_branch_returns_none_on_failure(self):
        """_get_current_branch returns None when git fails."""
        mod = self._import()
        proc = make_proc(returncode=128, stderr="not a git repository")
        with patch("subprocess.run", return_value=proc):
            result = mod._get_current_branch()
        assert result is None

    def test_get_current_branch_returns_none_on_detached_head(self):
        """_get_current_branch returns None when output is empty (detached HEAD)."""
        mod = self._import()
        proc = make_proc(stdout="", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_current_branch()
        assert result is None

    def test_get_current_branch_returns_branch_name(self):
        """_get_current_branch returns the branch name on success."""
        mod = self._import()
        proc = make_proc(stdout="feature/my-work\n", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod._get_current_branch()
        assert result == "feature/my-work"
