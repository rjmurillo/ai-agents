#!/usr/bin/env python3
"""Tests for Stop/invoke_auto_retrospective.py.

Covers:
- Retrospective file creation
- INDEX.md creation and update
- Idempotency (skip if retro exists for today)
- Trivial session bypass
- Consumer repo skip
- Bypass via environment variable
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

import invoke_auto_retrospective


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    """Create a minimal project directory tree with session log."""
    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / "sessions").mkdir()
    (agents / "retrospective").mkdir()

    # Create a non-trivial session log
    session_log = agents / "sessions" / "2026-01-01-session-001.json"
    session_data = {
        "objective": "Implement feature X",
        "outcomes": ["Feature X working", "Tests passing"],
        "work": [
            {"description": "Wrote implementation", "status": "done"},
            {"description": "Added tests", "status": "done"},
        ],
        "notes": "x" * 600,  # Padding to exceed 500-char trivial threshold
    }
    session_log.write_text(
        json.dumps(session_data, indent=2),
        encoding="utf-8",
    )
    return tmp_path


class TestRetroExistsToday:
    """Test _retro_exists_today helper."""

    def test_finds_existing_retro(self, tmp_path: Path) -> None:
        retro_dir = tmp_path / "retros"
        retro_dir.mkdir()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (retro_dir / f"{today}-auto-retro.md").write_text("retro", encoding="utf-8")

        assert invoke_auto_retrospective._retro_exists_today(retro_dir, today) is True

    def test_no_retro_today(self, tmp_path: Path) -> None:
        retro_dir = tmp_path / "retros"
        retro_dir.mkdir()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        assert invoke_auto_retrospective._retro_exists_today(retro_dir, today) is False

    def test_missing_dir(self, tmp_path: Path) -> None:
        assert (
            invoke_auto_retrospective._retro_exists_today(
                tmp_path / "nonexistent", "2026-01-01"
            )
            is False
        )


class TestIsTrivialSession:
    """Test _is_trivial_session helper."""

    def test_no_session_log_is_trivial(self) -> None:
        assert invoke_auto_retrospective._is_trivial_session(None) is True

    def test_short_session_is_trivial(self, tmp_path: Path) -> None:
        log = tmp_path / "short.json"
        log.write_text("{}", encoding="utf-8")
        assert invoke_auto_retrospective._is_trivial_session(log) is True

    def test_session_with_work_is_not_trivial(self, tmp_path: Path) -> None:
        log = tmp_path / "real.json"
        payload = {
            "work": [
                {"description": "Implement gate", "status": "in_progress"}
            ],
            "outcomes": [],
        }
        log.write_text(json.dumps(payload), encoding="utf-8")
        assert invoke_auto_retrospective._is_trivial_session(log) is False


class TestExtractSessionSummary:
    """Test _extract_session_summary helper."""

    def test_extracts_fields(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps({
                "objective": "Fix bug",
                "outcomes": ["Bug fixed"],
                "work": [{"description": "Debugged issue"}],
            }),
            encoding="utf-8",
        )

        result = invoke_auto_retrospective._extract_session_summary(log)
        assert result["objective"] == "Fix bug"
        assert "Bug fixed" in result["outcomes"]
        assert "Debugged issue" in result["work_items"]

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        log = tmp_path / "bad.json"
        log.write_text("not json", encoding="utf-8")

        result = invoke_auto_retrospective._extract_session_summary(log)
        assert result["objective"] == ""


class TestMain:
    """Test main() function."""

    def test_skip_consumer_repo(self) -> None:
        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_auto_retrospective.main()
            assert exc_info.value.code == 0

    def test_skip_via_env_var(self) -> None:
        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.dict("os.environ", {"SKIP_AUTO_RETRO": "true"}):
            with pytest.raises(SystemExit) as exc_info:
                invoke_auto_retrospective.main()
            assert exc_info.value.code == 0

    def test_skip_if_retro_exists(self, project_tree: Path) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        retro_dir = project_tree / ".agents" / "retrospective"
        (retro_dir / f"{today}-existing-retro.md").write_text(
            "existing", encoding="utf-8"
        )

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=project_tree,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_auto_retrospective.main()
            assert exc_info.value.code == 0

    def test_skip_trivial_session(self, tmp_path: Path) -> None:
        agents = tmp_path / ".agents"
        agents.mkdir()
        (agents / "retrospective").mkdir()
        (agents / "sessions").mkdir()

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=tmp_path,
        ), patch.object(
            invoke_auto_retrospective, "get_today_session_log", return_value=None,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_auto_retrospective.main()
            assert exc_info.value.code == 0

    def test_creates_retro_file(self, project_tree: Path) -> None:
        session_log = list(
            (project_tree / ".agents" / "sessions").glob("*.json")
        )[0]

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=project_tree,
        ), patch.object(
            invoke_auto_retrospective,
            "get_recent_session_log",
            return_value=session_log,
        ):
            invoke_auto_retrospective.main()

        retro_dir = project_tree / ".agents" / "retrospective"
        retro_files = list(retro_dir.glob("*auto-retro.md"))
        assert len(retro_files) >= 1
        content = retro_files[0].read_text(encoding="utf-8")
        assert "What Went Well" in content
        assert "Failure Patterns" in content

    def test_creates_index_file(self, project_tree: Path) -> None:
        session_log = list(
            (project_tree / ".agents" / "sessions").glob("*.json")
        )[0]

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=project_tree,
        ), patch.object(
            invoke_auto_retrospective,
            "get_recent_session_log",
            return_value=session_log,
        ):
            invoke_auto_retrospective.main()

        index = project_tree / "docs" / "retros" / "INDEX.md"
        assert index.exists()
        content = index.read_text(encoding="utf-8")
        assert "auto-retro" in content

    def test_retries_missing_index_when_retro_exists(
        self, project_tree: Path
    ) -> None:
        """A prior INDEX.md write failure must be recoverable.

        When the per-day retro markdown already exists but INDEX.md is
        missing the row for it, the next Stop hook invocation must
        append the row instead of short-circuiting on
        `_retro_exists_today`. Without this, an early INDEX.md failure
        is permanent because later runs skip the index update entirely.
        """
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        retro_dir = project_tree / ".agents" / "retrospective"
        filename = f"{today}-auto-retro.md"
        (retro_dir / filename).write_text("existing", encoding="utf-8")

        # INDEX.md does not exist yet, simulating a prior write failure
        # after the retro markdown was already on disk.
        index = project_tree / "docs" / "retros" / "INDEX.md"
        assert not index.exists()

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=project_tree,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_auto_retrospective.main()
            assert exc_info.value.code == 0

        assert index.exists()
        content = index.read_text(encoding="utf-8")
        assert filename in content

    def test_index_update_is_idempotent_across_runs(
        self, project_tree: Path
    ) -> None:
        """A second run with the row already present must not duplicate it."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        retro_dir = project_tree / ".agents" / "retrospective"
        filename = f"{today}-auto-retro.md"
        (retro_dir / filename).write_text("existing", encoding="utf-8")

        with patch.object(
            invoke_auto_retrospective, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_auto_retrospective,
            "_resolve_safe_project_path",
            return_value=project_tree,
        ):
            with pytest.raises(SystemExit):
                invoke_auto_retrospective.main()
            with pytest.raises(SystemExit):
                invoke_auto_retrospective.main()

        index = project_tree / "docs" / "retros" / "INDEX.md"
        content = index.read_text(encoding="utf-8")
        # Each row contains `filename` twice (link text + URL fragment),
        # so one row -> count of 2. Two rows would be count of 4.
        row_marker = f"| {today} | [{filename}]"
        assert content.count(row_marker) == 1


class TestFailOpen:
    """Test fail-open behavior of the script wrapper."""

    def test_exception_exits_zero(self) -> None:
        """The ``__main__`` wrapper must catch errors and exit 0.

        Validates the contract Claude Code relies on: even when ``main()``
        raises, the Stop hook must not block session stop.
        """
        from tests.hook_test_helpers import run_main_wrapper

        def raising_main() -> None:
            raise RuntimeError("boom")

        code, _stdout, stderr = run_main_wrapper(
            invoke_auto_retrospective, raising_main
        )
        assert code == 0
        assert "boom" in stderr
