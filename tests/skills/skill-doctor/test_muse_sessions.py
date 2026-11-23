#!/usr/bin/env python3
"""Tests for Muse session collection in skill-doctor."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_sessions import find_muse_session_files, parse_muse_session
from session_test_helpers import run_collector, write_jsonl

EPOCH_MICROS = 1795376976000000  # 2026-11-22T19:49:36Z


def muse_record(payload_type, payload, offset_micros=0):
    return {
        "payload_type": payload_type,
        "payload": payload,
        "recorded_at": EPOCH_MICROS + offset_micros,
    }


class MuseSessionTests(unittest.TestCase):
    def test_parses_metadata_user_intent_and_tool_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "22" / "session-1"
            path = session_dir / "session.jsonl"
            write_jsonl(
                path,
                [
                    {
                        "retained_frame": "session_permission_transaction",
                        "children": [
                            {
                                "child_index": 0,
                                "record_json": json.dumps(
                                    muse_record(
                                        "runtime.session.metadata",
                                        {
                                            "kind": "metadata",
                                            "record": {
                                                "build": {"semver": "1.4.25"},
                                                "workspace_root": "/tmp/repo",
                                            },
                                        },
                                    )
                                ),
                            }
                        ],
                    },
                    muse_record(
                        "runtime.user_intent.accepted",
                        {
                            "model_messages": [
                                {"content": [{"kind": "text", "text": "Fix the collector"}]}
                            ]
                        },
                        1000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {
                            "run_id": "run-1",
                            "record": {"tool_name": "read_file", "call_id": "call-1"},
                        },
                        2000000,
                    ),
                    muse_record(
                        "tool_batch.effect.terminal",
                        {
                            "run_id": "run-1",
                            "record": {"outcome": {"kind": "completed"}},
                        },
                        3000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {
                            "run_id": "run-1",
                            "record": {"tool_name": "edit_file", "call_id": "call-2"},
                        },
                        4000000,
                    ),
                    muse_record(
                        "tool_batch.effect.terminal",
                        {
                            "run_id": "run-1",
                            "record": {"outcome": {"kind": "failed"}},
                        },
                        5000000,
                    ),
                ],
            )

            meta, stats, entries, skills = parse_muse_session(path, {"update-skill"}, False)

            self.assertEqual(meta["id"], "session-1")
            self.assertEqual(meta["cwd"], "/tmp/repo")
            self.assertEqual(meta["originator"], "muse")
            self.assertEqual(meta["cli_version"], "1.4.25")
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["error_outputs"], 1)
            self.assertTrue(stats["has_code_edits"])
            self.assertEqual(skills, [])
            self.assertIn(("user", "Fix the collector"), entries)
            self.assertTrue(any(role == "tool:read_file" for role, _ in entries))

    def test_run_events_map_prose_args_outputs_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-run"
            path = session_dir / "session.jsonl"
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": {"workspace_root": "/tmp/repo"}},
                    ),
                    muse_record(
                        "runtime.user_intent.accepted",
                        {"model_messages": [{"content": [{"kind": "text", "text": "Do it"}]}]},
                        1000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {"kind": "assistant_message_committed", "text": "On it."},
                        },
                        2000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {
                                "kind": "assistant_tool_calls_committed",
                                "tool_calls": [
                                    {
                                        "name": "read_skill",
                                        "args": '{"name": "update-skill"}',
                                        "call_id": "call-1",
                                    }
                                ],
                            },
                        },
                        3000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {
                            "run_id": "run-1",
                            "record": {"tool_name": "read_skill", "call_id": "call-1"},
                        },
                        4000000,
                    ),
                    muse_record(
                        "tool_batch.effect.terminal",
                        {"run_id": "run-1", "record": {"outcome": {"kind": "completed"}}},
                        5000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {
                                "kind": "tool_result_batch_committed",
                                "results": [{"text": "skill body here"}],
                            },
                        },
                        6000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {"kind": "model_completed", "finish_reason": "stop"},
                        },
                        7000000,
                    ),
                ],
            )

            meta, stats, entries, skills = parse_muse_session(path, {"update-skill"}, False)

            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 1)
            self.assertEqual(skills, ["update-skill"])
            self.assertIn(("assistant", "On it."), entries)
            self.assertTrue(
                any(role == "tool:read_skill" and "update-skill" in text for role, text in entries)
            )
            self.assertTrue(
                any(role == "output" and "skill body here" in text for role, text in entries)
            )

    def test_run_commit_without_batch_still_emits_tool_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-commit-only"
            path = session_dir / "session.jsonl"
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": {"workspace_root": "/tmp/repo"}},
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {
                                "kind": "assistant_tool_calls_committed",
                                "tool_calls": [
                                    {
                                        "name": "bash",
                                        "args": '{"command": "ls"}',
                                        "call_id": "call-9",
                                    }
                                ],
                            },
                        },
                        1000000,
                    ),
                ],
            )

            _meta, stats, entries, _skills = parse_muse_session(path, set(), False)

            self.assertEqual(stats["tool_calls"], 1)
            self.assertEqual(sum(1 for role, _ in entries if role == "tool:bash"), 1)

    def test_model_completed_counts_text_only_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-text-only"
            path = session_dir / "session.jsonl"
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": {"workspace_root": "/tmp/repo"}},
                    ),
                    muse_record(
                        "runtime.user_intent.accepted",
                        {"model_messages": [{"content": [{"kind": "text", "text": "Hi"}]}]},
                        1000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-9",
                            "event": {"kind": "model_completed", "finish_reason": "stop"},
                        },
                        2000000,
                    ),
                ],
            )

            _meta, stats, _entries, _skills = parse_muse_session(path, set(), False)

            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 0)

    def test_malformed_nested_records_do_not_halt_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-bad" / "session.jsonl"
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": ["unexpected"]},
                    ),
                    muse_record(
                        "runtime.user_intent.accepted",
                        {
                            "model_messages": [
                                {"content": [{"kind": "text", "text": "Still works"}]}
                            ]
                        },
                        1000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {"run_id": "run-1", "record": {"tool_name": "bash", "call_id": "c1"}},
                        2000000,
                    ),
                ],
            )

            meta, stats, entries, _skills = parse_muse_session(path, set(), False)

            self.assertIsNone(meta["cwd"])
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["tool_calls"], 1)
            self.assertIn(("user", "Still works"), entries)

    def test_returns_none_without_retained_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-2" / "session.jsonl"
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": {"workspace_root": "/tmp/repo"}},
                    )
                ],
            )

            self.assertIsNone(parse_muse_session(path, set(), False))

    def test_finds_recent_session_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            muse_home = Path(tmp)
            recent = muse_home / "sessions" / "2026" / "11" / "22" / "recent" / "session.jsonl"
            old = muse_home / "sessions" / "2026" / "11" / "12" / "old" / "session.jsonl"
            for path in (recent, old):
                write_jsonl(path, [{"payload_type": "session.started", "payload": {}}])
            old_time = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
            os.utime(old, (old_time, old_time))
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

            files = find_muse_session_files(muse_home, cutoff)

            self.assertEqual([path for _, path in files], [recent])


def test_cli_collects_muse_sessions(tmp_path):
    home = tmp_path / "muse-home"
    repo = tmp_path / "repo"
    repo.mkdir()
    session_dir = home / "sessions" / "2026" / "11" / "22" / "cli-session-1"
    write_jsonl(
        session_dir / "session.jsonl",
        [
            muse_record(
                "runtime.session.metadata",
                {"kind": "metadata", "record": {"workspace_root": str(repo)}},
            ),
            muse_record(
                "runtime.user_intent.accepted",
                {"model_messages": [{"content": [{"kind": "text", "text": "Do the work"}]}]},
                1000000,
            ),
            muse_record(
                "tool_batch.effect.started",
                {"run_id": "run-1", "record": {"tool_name": "bash", "call_id": "call-1"}},
                2000000,
            ),
            muse_record(
                "tool_batch.effect.terminal",
                {"run_id": "run-1", "record": {"outcome": {"kind": "completed"}}},
                3000000,
            ),
        ],
    )
    # The collector skips sessions idle for less than the default window.
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(session_dir / "session.jsonl", (old, old))

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "muse",
        "--muse-home",
        str(home),
        "--repo",
        str(repo),
        "--min-idle-minutes",
        "0",
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["harness"] == "muse"
    assert inventory["sources"]["muse"]["records_in_window"] == 1
    assert [s["meta"]["id"] for s in inventory["sessions"]] == ["cli-session-1"]
    assert inventory["sessions"][0]["harness"] == "muse"
    assert inventory["muse_home"] == str(home)


def _write_working_session(home, repo, session_id):
    session_dir = home / "sessions" / "2026" / "11" / "22" / session_id
    path = session_dir / "session.jsonl"
    write_jsonl(
        path,
        [
            muse_record(
                "runtime.session.metadata",
                {"kind": "metadata", "record": {"workspace_root": str(repo)}},
            ),
            muse_record(
                "runtime.user_intent.accepted",
                {"model_messages": [{"content": [{"kind": "text", "text": "Do the work"}]}]},
                1000000,
            ),
            muse_record(
                "tool_batch.effect.started",
                {"run_id": "run-1", "record": {"tool_name": "bash", "call_id": "call-1"}},
                2000000,
            ),
        ],
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(path, (old, old))
    return path


def test_cli_malformed_muse_session_does_not_block_healthy_one(tmp_path):
    home = tmp_path / "muse-home"
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_working_session(home, repo, "healthy-1")
    bad_dir = home / "sessions" / "2026" / "11" / "22" / "bad-1"
    write_jsonl(
        bad_dir / "session.jsonl",
        [muse_record("runtime.session.metadata", {"kind": "metadata", "record": ["x"]})],
    )

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "muse",
        "--muse-home",
        str(home),
        "--repo",
        str(repo),
        "--min-idle-minutes",
        "0",
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert [s["meta"]["id"] for s in inventory["sessions"]] == ["healthy-1"]
    assert inventory["collection_status"] == "partial"


def test_cli_discovers_muse_config_global_skills(tmp_path):
    home = tmp_path / "muse-home"
    config_home = tmp_path / "muse-config"
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_working_session(home, repo, "cli-session-1")
    skill = config_home / "skills" / "config-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\ndescription: Test skill\n---\n", encoding="utf-8")

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "muse",
        "--muse-home",
        str(home),
        "--muse-config-home",
        str(config_home),
        "--repo",
        str(repo),
        "--min-idle-minutes",
        "0",
        "--include-global-skills",
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    names = {skill["name"] for skill in inventory["skills"]}
    assert "config-skill" in names


if __name__ == "__main__":
    unittest.main()
