"""Synthetic journals exercise the same CLI shipped to plugin consumers."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from collect_sessions import (
    discover_skills,
    discover_warp_databases,
    find_copilot_session_files,
    open_warp_database,
    parse_copilot_session,
    session_matches_repo,
)
from session_test_helpers import run_collector

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "src" / "claude" / "skills" / "skill-doctor" / "scripts"


def event(kind, data, **extra):
    return {"type": kind, "timestamp": "2026-11-09T12:00:00Z", "data": data, **extra}


def journal(home, repo, extra=(), session="session-1", context=True):
    path = home / "session-state" / session / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        event(
            "session.start",
            {
                "sessionId": "../../escape",
                "context": {"cwd": str(repo)} if context else {},
                "copilotVersion": "1.0.108-1",
            },
        ),
        event("user.message", {"content": "Fix the parser."}),
        event(
            "assistant.message",
            {
                "content": "Reading the parser.",
                "toolRequests": [
                    {"toolCallId": "one", "name": "view", "arguments": {"path": "parser.py"}}
                ],
            },
        ),
        event(
            "tool.execution_start",
            {"toolCallId": "one", "toolName": "view", "arguments": {"path": "parser.py"}},
        ),
        event(
            "tool.execution_complete",
            {"toolCallId": "one", "success": True, "result": {"content": "Parser source."}},
        ),
        *extra,
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_parser_tracks_calls_failures_edits_and_explicit_skills(tmp_path):
    home, repo = tmp_path / "home", tmp_path / "project"
    extra = [
        event("skill.invoked", {"name": "repair", "content": "Do not copy this skill body."}),
        event("tool.execution_start", {"toolName": "apply_patch", "arguments": {"input": "patch"}}),
        event("tool.execution_start", {"toolName": "view", "arguments": {"path": "parser.py"}}),
        event("tool.execution_complete", {"success": False, "error": {"message": "Access denied"}}),
        event("assistant.message_delta", {"deltaContent": "Do not duplicate this."}),
        event("model.messages_snapshot", {"messages": ["Do not copy this."]}),
        event("instruction.update", {"content": "Catalog mentions skills/not-used/SKILL.md"}),
        event(
            "tool.execution_complete",
            {
                "success": True,
                "result": {"content": [{"type": "text", "text": "Unicode result: \u00e9"}]},
            },
        ),
    ]
    parsed = parse_copilot_session(journal(home, repo, extra), {"repair", "not-used"}, False)
    meta, stats, entries, skills = parsed
    assert meta["id"] == "session-1"
    assert meta["cwd"] == str(repo)
    assert meta["cli_version"] == "1.0.108-1"
    assert stats["user_turns"] == stats["assistant_turns"] == 1
    assert stats["tool_calls"] == 3
    assert stats["repeated_tool_calls"] == stats["error_outputs"] == 1
    assert stats["has_code_edits"] is True
    assert skills == ["repair"]
    text = "\n".join(text for _, text in entries)
    assert "Access denied" in text and "\u00e9" in text
    assert "Do not" not in text and "not-used" not in text


@pytest.mark.parametrize("include_children,expected", [(False, 1), (True, 3)])
def test_children_replay_and_duplicate_events(tmp_path, include_children, expected):
    repeated = event("tool.execution_start", {"toolName": "view", "arguments": {}}, id="same")
    extra = [
        repeated,
        repeated,
        event("tool.execution_start", {"toolName": "create"}, agentId="child"),
        event(
            "tool.execution_start",
            {"toolName": "edit", "parentToolCallId": "parent", "toolCallId": "old-child"},
        ),
        event("tool.execution_complete", {"toolCallId": "old-child", "success": False}),
        event("assistant.message", {"content": "Replay"}, checkpoint=True),
        event("assistant.message", {"content": "Transient"}, ephemeral=True),
    ]
    path = journal(tmp_path / "home", tmp_path, extra)
    _, stats, entries, _ = parse_copilot_session(path, set(), include_children)
    assert stats["tool_calls"] == expected + 1
    assert stats["error_outputs"] == int(include_children)
    assert stats["has_code_edits"] is include_children
    assert stats["assistant_turns"] == 1
    assert not any(text in {"Replay", "Transient"} for _, text in entries)


def test_discovery_uses_journal_mtime_and_only_top_level_sessions(tmp_path):
    home = tmp_path / "home"
    recent = journal(home, tmp_path)
    old = journal(home, tmp_path, session="old")
    os.utime(old, (0, 0))
    nested = old.parent / "checkpoints" / "nested"
    nested.mkdir(parents=True)
    (nested / "events.jsonl").write_text("{}", encoding="utf-8")
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    assert [path for _, path in find_copilot_session_files(home, cutoff)] == [recent]
    assert find_copilot_session_files(tmp_path / "absent", cutoff) == []


def test_missing_malformed_and_long_journals(tmp_path):
    assert parse_copilot_session(tmp_path / "missing", set(), False) is None
    path = journal(
        tmp_path / "home",
        tmp_path,
        [event("assistant.message", {"content": "x" * 10000}) for _ in range(190)],
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write('invalid\nnull\n[]\n{"type":"user.message","data":null}\n{"partial":')
    _, stats, entries, _ = parse_copilot_session(path, set(), False)
    assert stats["assistant_turns"] == 191
    assert len(entries) <= 161
    assert any("entries omitted" in text for _, text in entries)
    assert max(map(len, (text for _, text in entries))) < 1700


def test_copilot_project_global_and_plugin_skill_discovery(tmp_path):
    repo, home = tmp_path / "repo", tmp_path / "copilot"
    roots = [
        repo / ".github" / "skills" / "project",
        home / "skills" / "personal",
        home / "installed-plugins" / "market" / "plugin" / "skills" / "bundled",
    ]
    for root in roots:
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("description: Synthetic skill\n", encoding="utf-8")
    assert set(discover_skills([repo], tmp_path / "codex", [], False, copilot_home=home)) == {
        "project"
    }
    found = discover_skills([repo], tmp_path / "codex", [], True, copilot_home=home)
    assert {"project", "personal", "bundled"} <= set(found)


def test_auto_collection_skips_non_object_claude_rows_and_keeps_copilot(tmp_path):
    repo, home = tmp_path / "repo", tmp_path / "copilot"
    repo.mkdir()
    journal(home, repo)
    claude_home = tmp_path / "claude"
    path = claude_home / "projects" / "repo" / "session.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('null\n[]\ntrue\n7\n"not an event"\n', encoding="utf-8")

    result = run_collector(tmp_path, home, "--repo", str(repo), "--claude-home", str(claude_home))

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["sources"]["claude"]["records_in_window"] == 1
    assert [session["harness"] for session in inventory["sessions"]] == ["copilot"]


@pytest.mark.parametrize("override", ["argument", "environment"])
@pytest.mark.parametrize("include_global", [False, True])
def test_cli_discovers_global_skills_only_in_resolved_claude_home(
    tmp_path, override, include_global
):
    repo, home = tmp_path / "repo", tmp_path / "copilot"
    repo.mkdir()
    journal(home, repo)
    isolated_home = tmp_path / "isolated-home"
    claude_home = (
        tmp_path / "custom-claude"
        if override == "argument"
        else isolated_home / "claude_config_dir"
    )
    for root, name in (
        (claude_home, "custom"),
        (isolated_home / ".claude", "wrong-home"),
    ):
        skill = root / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("description: Synthetic skill\n", encoding="utf-8")
    args = ["--repo", str(repo), "--harness", "copilot"]
    if override == "argument":
        args.extend(["--claude-home", str(claude_home)])
    if include_global:
        args.append("--include-global-skills")

    result = run_collector(tmp_path, home, *args)

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert {skill["name"] for skill in inventory["skills"]} == (
        {"custom"} if include_global else set()
    )


@pytest.mark.parametrize("root", ["claude", "copilot-cli"])
@pytest.mark.parametrize("selection", ["copilot", "auto", "all"])
def test_cli_collects_from_unrelated_cwd_and_respects_repo_scope(tmp_path, root, selection):
    repo, home = tmp_path / "project with spaces \u65e5\u672c\u8a9e", tmp_path / "copilot"
    skill = repo / ".github" / "skills" / "repair"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: Repair parser\n", encoding="utf-8")
    journal(
        home,
        repo,
        [
            event("skill.invoked", {"name": "repair"}),
            event("assistant.message", {"content": "Unicode transcript: \u65e5\u672c\u8a9e"}),
        ],
    )
    journal(home, tmp_path / "other", session="other")
    out = tmp_path / "report"
    assert not out.exists()
    result = run_collector(
        tmp_path,
        home,
        "--harness",
        selection,
        "--repo",
        str(repo),
        "--claude-home",
        str(tmp_path / "none"),
        "--codex-home",
        str(tmp_path / "none"),
        "--pi-home",
        str(tmp_path / "none"),
        "--grok-home",
        str(tmp_path / "none"),
        "--zcode-home",
        str(tmp_path / "none"),
        "--hermes-home",
        str(tmp_path / "none"),
        root=root,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["sources"]["copilot"]["records_in_window"] == 2
    assert inventory["stats"]["sessions_sampled"] == 1
    assert inventory["skill_usage"]["repair"] == 1
    session = inventory["sessions"][0]
    assert session["harness"] == "copilot"
    transcript = Path(session["transcript_path"]).read_text(encoding="utf-8")
    assert "[tool:view]" in transcript and "[skill]" in transcript
    assert "\u65e5\u672c\u8a9e" in transcript
    assert not (tmp_path / "escape.md").exists()


def test_context_changes_fill_missing_context_and_non_string_identifiers(tmp_path):
    repo = tmp_path / "project"
    extra = [
        event("session.context_changed", {"cwd": {"bad": "path"}}),
        event("session.context_changed", {"cwd": str(repo / "changed")}),
        event("user.message", {"content": "Changed context."}, id=["not", "an", "id"]),
        event("tool.execution_start", {"toolName": "view", "toolCallId": {"bad": "id"}}),
        event("tool.execution_complete", {"toolCallId": ["bad"], "success": True}),
        event("assistant.message", {"content": "Still readable."}, id={"bad": "id"}),
    ]
    meta, stats, entries, _ = parse_copilot_session(
        journal(tmp_path / "home", repo, extra, context=False), set(), False
    )
    assert meta["cwd"] == str(repo / "changed")
    assert stats["user_turns"] == stats["assistant_turns"] == stats["tool_calls"] == 2
    assert ("assistant", "Still readable.") in entries


@pytest.mark.parametrize("scope", ["first", "second", "all"])
def test_cli_keeps_mixed_repository_sessions_out_of_project_scope(tmp_path, scope):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    home = tmp_path / "home"
    journal(
        home,
        first,
        [
            event("session.context_changed", {"context": {"cwd": str(second)}}),
            event("tool.execution_complete", {"success": False, "error": {"message": "failed"}}),
        ],
    )
    args = (
        ["--all-conversations"]
        if scope == "all"
        else ["--repo", str(first if scope == "first" else second)]
    )
    result = run_collector(tmp_path, home, "--harness", "copilot", *args)
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert len(inventory["sessions"]) == int(scope == "all")
    if scope == "all":
        session = inventory["sessions"][0]
        assert session["meta"]["cwd_history"] == [str(first), str(second)]
        assert session["stats"]["error_outputs"] == 1


def test_cli_preserves_context_changes_within_one_repository(tmp_path):
    repo = tmp_path / "project"
    child = repo / "src"
    child.mkdir(parents=True)
    home = tmp_path / "home"
    journal(
        home,
        repo,
        [
            event("session.context_changed", {"cwd": str(child)}),
            event("session.context_changed", {"cwd": str(repo)}),
        ],
    )
    result = run_collector(tmp_path, home, "--harness", "copilot", "--repo", str(repo))
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert len(inventory["sessions"]) == 1
    assert inventory["sessions"][0]["meta"]["cwd_history"] == [str(repo), str(child)]


def test_relative_script_launch_fails_from_unrelated_cwd(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/collect_sessions.py", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "can't open file" in result.stderr


def test_cli_missing_empty_override_and_argument_conflict(tmp_path):
    home = tmp_path / "home"
    missing = run_collector(tmp_path, home, "--harness", "copilot")
    assert missing.returncode == 1 and "not found" in missing.stderr
    (home / "session-state").mkdir(parents=True)
    empty = run_collector(
        tmp_path,
        tmp_path / "ignored",
        "--harness",
        "copilot",
        "--copilot-home",
        str(home),
        "--all-conversations",
    )
    assert empty.returncode == 0, empty.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["stats"]["sessions_sampled"] == 0
    conflict = run_collector(tmp_path, home, "--all-conversations", "--repo", str(tmp_path))
    assert conflict.returncode == 2 and "cannot be combined" in conflict.stderr


@pytest.mark.parametrize(
    "recorded,expected",
    [
        (r"C:\Users\someone\Project\src", True),
        ("C:/Users/someone/Project/src", True),
        (r"\\server\share\Project\src", True),
        (r"D:\worktrees\PROJECT\src", True),
        ("/home/someone/Project/src", True),
        ("/Users/someone/Project/src", True),
        ("/home/someone/project/src", False),
        (r"C:\Users\someone\Other\src", False),
        ("/home/someone/Other/src", False),
        ("", False),
    ],
)
def test_repository_filter_preserves_recorded_os_path_rules(
    tmp_path, monkeypatch, recorded, expected
):
    """AC-P1: Imported journals retain their source OS's path semantics."""
    repo = tmp_path / "Project"
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert session_matches_repo(recorded, repo) is expected


def test_cli_unicode_paths_survive_legacy_output_encoding(tmp_path, monkeypatch):
    """AC-P2: A legacy Windows pipe cannot turn successful collection into failure."""
    root = tmp_path / "report with spaces \u65e5\u672c\u8a9e"
    root.mkdir()
    home = root / "copilot"
    journal(home, root)
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")

    result = run_collector(root, home, "--harness", "copilot", "--all-conversations")

    assert result.returncode == 0, result.stderr
    inventory = json.loads((root / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["stats"]["sessions_sampled"] == 1
    assert inventory["sessions"][0]["meta"]["cwd"] == str(root)


@pytest.mark.parametrize(
    "platform,relative_root",
    [
        ("darwin", "Library/Group Containers/2BBY89MBSN.dev.warp/Library/Application Support"),
        ("linux", ".local/share/warp-terminal"),
        ("win32", "AppData/Roaming/Warp"),
    ],
)
def test_warp_discovery_uses_platform_data_roots(tmp_path, monkeypatch, platform, relative_root):
    """AC-P3: Exercise each discovery branch without replacing native pathlib."""
    monkeypatch.setattr("collect_sessions.sys.platform", platform)
    monkeypatch.setattr(
        "collect_sessions.os",
        SimpleNamespace(name="nt" if platform == "win32" else "posix", environ=os.environ),
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    database = tmp_path / relative_root / "stable" / "warp.sqlite"
    database.parent.mkdir(parents=True)
    database.touch()

    assert discover_warp_databases() == [database.resolve()]
    override = tmp_path / "custom data" / "preview" / "warp.sqlite"
    override.parent.mkdir(parents=True)
    override.touch()
    assert discover_warp_databases(data_dir=override.parent.parent) == [override.resolve()]


def test_warp_sqlite_handles_unicode_and_uri_metacharacters_read_only(tmp_path):
    """AC-P2, AC-P3: Read-only SQLite URIs preserve filesystem path bytes."""
    database = tmp_path / "Warp # space \u65e5\u672c\u8a9e.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE probe (value TEXT)")
        connection.execute("INSERT INTO probe VALUES ('kept')")
        connection.commit()

    with closing(open_warp_database(database)) as connection:
        assert connection.execute("SELECT value FROM probe").fetchone()["value"] == "kept"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM probe")


@pytest.mark.parametrize("all_conversations", [False, True])
def test_git_discovery_preserves_unicode_repository_paths(tmp_path, monkeypatch, all_conversations):
    """AC-P2: Git emits UTF-8 paths even when Windows Python uses a legacy locale."""
    root = tmp_path / "git project \u65e5\u672c\u8a9e"
    initialized = subprocess.run(
        ["git", "init", str(root)], capture_output=True, timeout=30, check=False
    )
    assert initialized.returncode == 0, initialized.stderr
    skill = root / ".github" / "skills" / "repair"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("description: Repair parser\n", encoding="utf-8")
    home = root / "copilot"
    journal(home, root, [event("skill.invoked", {"name": "repair"})])
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252:backslashreplace")
    args = ["--all-conversations"] if all_conversations else []

    result = run_collector(root, home, "--harness", "copilot", *args)

    assert result.returncode == 0, result.stderr
    inventory = json.loads((root / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["repos"] == [str(root.resolve())]
    assert inventory["skill_usage"]["repair"] == 1
