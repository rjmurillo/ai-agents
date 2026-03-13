"""Tests for trace reconstruction utility.

Validates that multi-agent call graphs can be reconstructed from session
logs containing traceId and parentSessionId fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.traceability.reconstruct_trace import (
    SessionNode,
    build_tree,
    collect_traced_sessions,
    format_json,
    format_mermaid,
    format_text,
    main,
    session_id_from_filename,
)

TRACE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _make_session_log(
    number: int,
    trace_id: str = "",
    parent_session_id: str = "",
    objective: str = "test objective",
) -> dict:
    """Build a minimal session log dict with optional trace fields."""
    session: dict = {
        "number": number,
        "date": "2026-03-09",
        "branch": "feat/test",
        "startingCommit": "abc1234",
        "objective": objective,
    }
    if trace_id:
        session["traceId"] = trace_id
    if parent_session_id:
        session["parentSessionId"] = parent_session_id

    return {
        "session": session,
        "protocolCompliance": {
            "sessionStart": {},
            "sessionEnd": {},
        },
        "workLog": [],
    }


@pytest.fixture()
def sessions_dir(tmp_path: Path) -> Path:
    """Create a temp sessions directory with traced session logs."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()

    # Root session (orchestrator)
    root = _make_session_log(700, trace_id=TRACE_ID, objective="Orchestrate feature X")
    (sessions / "2026-03-09-session-700.json").write_text(json.dumps(root))

    # Child session (implementer)
    child1 = _make_session_log(
        701,
        trace_id=TRACE_ID,
        parent_session_id="2026-03-09-session-700",
        objective="Implement feature X",
    )
    (sessions / "2026-03-09-session-701.json").write_text(json.dumps(child1))

    # Child session (qa)
    child2 = _make_session_log(
        702,
        trace_id=TRACE_ID,
        parent_session_id="2026-03-09-session-700",
        objective="Test feature X",
    )
    (sessions / "2026-03-09-session-702.json").write_text(json.dumps(child2))

    # Unrelated session (no trace)
    unrelated = _make_session_log(703, objective="Unrelated work")
    (sessions / "2026-03-09-session-703.json").write_text(json.dumps(unrelated))

    return sessions


class TestSessionIdFromFilename:
    def test_extracts_stem(self) -> None:
        path = Path("2026-03-09-session-700.json")
        assert session_id_from_filename(path) == "2026-03-09-session-700"


class TestCollectTracedSessions:
    def test_groups_by_trace_id(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        assert TRACE_ID in traces
        assert len(traces[TRACE_ID]) == 3

    def test_excludes_untraced_sessions(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        all_ids = [n.session_id for nodes in traces.values() for n in nodes]
        assert "2026-03-09-session-703" not in all_ids

    def test_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert collect_traced_sessions(empty) == {}

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        assert collect_traced_sessions(tmp_path / "nope") == {}


class TestBuildTree:
    def test_links_children_to_parent(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        assert len(roots) == 1
        root = roots[0]
        assert root.session_id == "2026-03-09-session-700"
        assert len(root.children) == 2

    def test_child_session_ids(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        child_ids = {c.session_id for c in roots[0].children}
        assert child_ids == {"2026-03-09-session-701", "2026-03-09-session-702"}

    def test_orphan_nodes_become_roots(self) -> None:
        nodes = [
            SessionNode("s1", TRACE_ID, "", "feat/x", "root", "2026-03-09"),
            SessionNode("s2", TRACE_ID, "missing-parent", "feat/x", "orphan", "2026-03-09"),
        ]
        roots = build_tree(nodes)
        assert len(roots) == 2


class TestFormatText:
    def test_includes_trace_id(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        output = format_text(roots, TRACE_ID)
        assert TRACE_ID in output

    def test_shows_hierarchy(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        output = format_text(roots, TRACE_ID)
        assert "|- " in output
        assert "Orchestrate feature X" in output
        assert "Implement feature X" in output


class TestFormatJson:
    def test_valid_json(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        output = format_json(roots, TRACE_ID)
        data = json.loads(output)
        assert data["traceId"] == TRACE_ID
        assert len(data["roots"]) == 1
        assert len(data["roots"][0]["children"]) == 2


class TestFormatMermaid:
    def test_mermaid_syntax(self, sessions_dir: Path) -> None:
        traces = collect_traced_sessions(sessions_dir)
        roots = build_tree(traces[TRACE_ID])
        output = format_mermaid(roots, TRACE_ID)
        assert output.startswith("graph TD")
        assert "-->" in output


class TestMain:
    def test_no_sessions_dir(self, tmp_path: Path) -> None:
        exit_code = main(["--sessions-dir", str(tmp_path / "nonexistent")])
        assert exit_code == 2

    def test_no_traced_sessions(self, tmp_path: Path) -> None:
        empty = tmp_path / "sessions"
        empty.mkdir()
        # Write a session without traceId
        log = _make_session_log(1)
        (empty / "2026-03-09-session-1.json").write_text(json.dumps(log))
        exit_code = main(["--sessions-dir", str(empty)])
        assert exit_code == 1

    def test_specific_trace_id(self, sessions_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--sessions-dir", str(sessions_dir), "--trace-id", TRACE_ID])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert TRACE_ID in captured.out

    def test_missing_trace_id(self, sessions_dir: Path) -> None:
        exit_code = main(["--sessions-dir", str(sessions_dir), "--trace-id", "nonexistent"])
        assert exit_code == 1

    def test_json_format(self, sessions_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--sessions-dir", str(sessions_dir), "--format", "json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["traceId"] == TRACE_ID

    def test_all_traces(self, sessions_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--sessions-dir", str(sessions_dir)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Orchestrate feature X" in captured.out
