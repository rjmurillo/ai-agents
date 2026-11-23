#!/usr/bin/env python3
"""Tests for Muse run-event mapping in skill-doctor."""

import tempfile
import unittest
from pathlib import Path

from collect_sessions import parse_muse_session
from session_test_helpers import write_jsonl

EPOCH_MICROS = 1795376976000000  # 2026-11-22T19:49:36Z


def muse_record(payload_type, payload, offset_micros=0):
    return {
        "payload_type": payload_type,
        "payload": payload,
        "recorded_at": EPOCH_MICROS + offset_micros,
    }


class MuseRunEventTests(unittest.TestCase):
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
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(sum(1 for role, _ in entries if role == "tool:bash"), 1)

    def test_malformed_call_ids_do_not_halt_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-bad-ids"
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
                        {"model_messages": [{"content": [{"kind": "text", "text": "Go"}]}]},
                        1000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": "run-1",
                            "event": {
                                "kind": "assistant_tool_calls_committed",
                                "tool_calls": [
                                    {"name": "bash", "args": "{}", "call_id": []},
                                    {"name": "bash", "args": '{"x": 1}', "call_id": "ok-1"},
                                ],
                            },
                        },
                        2000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {"run_id": "run-1", "record": {"tool_name": "bash", "call_id": []}},
                        3000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {"run_id": "run-1", "record": {"tool_name": "bash", "call_id": "ok-1"}},
                        4000000,
                    ),
                ],
            )

            _meta, stats, entries, _skills = parse_muse_session(path, set(), False)

            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertTrue(
                any(role == "tool:bash" and '{"x": 1}' in text for role, text in entries)
            )

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

    def test_repeated_commit_only_id_emits_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-dup"
            path = session_dir / "session.jsonl"
            commit = muse_record(
                "runtime.session",
                {
                    "kind": "run",
                    "run_id": "run-1",
                    "event": {
                        "kind": "assistant_tool_calls_committed",
                        "tool_calls": [
                            {"name": "bash", "args": '{"x": 1}', "call_id": "dup-1"},
                            {"name": "bash", "args": '{"x": 1}', "call_id": "dup-1"},
                        ],
                    },
                },
            )
            write_jsonl(
                path,
                [
                    muse_record(
                        "runtime.session.metadata",
                        {"kind": "metadata", "record": {"workspace_root": "/tmp/repo"}},
                    ),
                    muse_record(
                        "runtime.user_intent.accepted",
                        {"model_messages": [{"content": [{"kind": "text", "text": "Go"}]}]},
                        1000000,
                    ),
                    commit,
                    commit,
                ],
            )

            _meta, stats, entries, _skills = parse_muse_session(path, set(), False)

            self.assertEqual(stats["tool_calls"], 1)
            self.assertEqual(stats["repeated_tool_calls"], 0)
            self.assertEqual(sum(1 for role, _ in entries if role == "tool:bash"), 1)

    def test_malformed_run_id_keeps_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "2026" / "11" / "23" / "session-bad-run"
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
                        {"model_messages": [{"content": [{"kind": "text", "text": "Go"}]}]},
                        1000000,
                    ),
                    muse_record(
                        "runtime.session",
                        {
                            "kind": "run",
                            "run_id": [],
                            "event": {
                                "kind": "assistant_tool_calls_committed",
                                "tool_calls": [
                                    {"name": "bash", "args": '{"x": 1}', "call_id": "c-1"}
                                ],
                            },
                        },
                        2000000,
                    ),
                    muse_record(
                        "tool_batch.effect.started",
                        {"run_id": [], "record": {"tool_name": "bash", "call_id": "c-2"}},
                        3000000,
                    ),
                ],
            )

            _meta, stats, _entries, _skills = parse_muse_session(path, set(), False)

            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["assistant_turns"], 0)


if __name__ == "__main__":
    unittest.main()
