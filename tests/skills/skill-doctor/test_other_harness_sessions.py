#!/usr/bin/env python3
"""Tests for skill-doctor session collection."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_sessions import (
    find_grok_session_files,
    find_pi_session_files,
    parse_grok_session,
    parse_pi_session,
    parse_zcode_session,
)
from session_test_helpers import (
    write_jsonl,
)


class PiSessionTests(unittest.TestCase):
    def test_parses_messages_tools_skills_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-20T10-00-00-000Z_session-1.jsonl"
            write_jsonl(
                path,
                [
                    {
                        "type": "session",
                        "id": "session-1",
                        "cwd": "/tmp/repo",
                        "timestamp": "2026-08-20T10:00:00.000Z",
                    },
                    {"type": "model_change", "provider": "zai", "modelId": "glm"},
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:01.000Z",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "Improve my skill"}],
                        },
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:02.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "thinking", "thinking": "plan the edit"},
                                {"type": "text", "text": "I will inspect it."},
                                {
                                    "type": "toolCall",
                                    "name": "read",
                                    "arguments": {
                                        "path": "/repo/.agents/skills/update-skill/SKILL.md"
                                    },
                                },
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:03.000Z",
                        "message": {
                            "role": "toolResult",
                            "toolName": "read",
                            "content": [{"type": "text", "text": "--- description: alpha"}],
                        },
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:04.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "toolCall",
                                    "name": "edit",
                                    "arguments": {
                                        "path": "/tmp/repo/SKILL.md",
                                        "oldText": "a",
                                        "newText": "b",
                                    },
                                },
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:05.000Z",
                        "message": {
                            "role": "toolResult",
                            "toolName": "edit",
                            "content": [
                                {"type": "text", "text": "oldText not found", "isError": True}
                            ],
                        },
                    },
                ],
            )

            meta, stats, entries, skills = parse_pi_session(path, {"update-skill"}, False)

            self.assertEqual(meta["id"], "session-1")
            self.assertEqual(meta["cwd"], "/tmp/repo")
            self.assertEqual(meta["originator"], "pi")
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 2)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["repeated_tool_calls"], 0)
            self.assertEqual(stats["error_outputs"], 1)
            self.assertTrue(stats["has_code_edits"])
            self.assertEqual(stats["first_ts"], "2026-08-20T10:00:00.000Z")
            self.assertEqual(stats["last_ts"], "2026-08-20T10:00:05.000Z")
            self.assertEqual(skills, ["update-skill"])
            self.assertIn(("user", "Improve my skill"), entries)
            self.assertIn(("assistant", "I will inspect it."), entries)
            self.assertIn(("output", "--- description: alpha"), entries)
            self.assertFalse(any(role == "thinking" for role, _ in entries))

    def test_accepts_include_subagents_without_changing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-2.jsonl"
            write_jsonl(
                path,
                [
                    {
                        "type": "session",
                        "id": "session-2",
                        "cwd": "/tmp/repo",
                        "timestamp": "2026-08-20T10:00:00.000Z",
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-08-20T10:00:01.000Z",
                        "message": {"role": "user", "content": "Hello there"},
                    },
                ],
            )

            without_flag = parse_pi_session(path, set(), False)
            with_flag = parse_pi_session(path, set(), True)

            self.assertEqual(without_flag, with_flag)
            self.assertEqual(with_flag[0]["originator"], "pi")

    def test_finds_recent_session_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            pi_home = Path(tmp)
            recent = pi_home / "sessions" / "--tmp-repo" / "recent.jsonl"
            old = pi_home / "sessions" / "--tmp-repo" / "old.jsonl"
            for path in (recent, old):
                write_jsonl(path, [{"type": "session", "id": "x"}])
            old_time = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
            os.utime(old, (old_time, old_time))
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

            files = find_pi_session_files(pi_home, cutoff)

            self.assertEqual([path for _, path in files], [recent])


class GrokSessionTests(unittest.TestCase):
    def test_parses_tool_calls_and_skips_synthetic_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            grok_home = Path(tmp)
            session_dir = grok_home / "sessions" / "%2Ftmp%2Frepo" / "abc-123"
            path = session_dir / "chat_history.jsonl"
            write_jsonl(
                path,
                [
                    {"type": "system", "content": "You are Grok."},
                    {
                        "type": "user",
                        "synthetic_reason": "system_reminder",
                        "content": [
                            {"type": "text", "text": "<system-reminder>skills</system-reminder>"}
                        ],
                    },
                    {"type": "user", "content": "Fix the collector"},
                    {
                        "type": "reasoning",
                        "id": "rs-1",
                        "summary": "[]",
                        "encrypted_content": "xx",
                        "status": "completed",
                    },
                    {
                        "type": "assistant",
                        "content": "I will read the skill.",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "name": "read_file",
                                "arguments": '{"path": "/repo/.grok/skills/update-skill/SKILL.md"}',
                            }
                        ],
                    },
                    {"type": "tool_result", "tool_call_id": "call-1", "content": "file body"},
                    {
                        "type": "assistant",
                        "content": "Now writing the file.",
                        "tool_calls": [
                            {
                                "id": "call-2",
                                "name": "write",
                                "arguments": '{"path": "/tmp/repo/out.txt", "content": "hi"}',
                            }
                        ],
                    },
                ],
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

            files = find_grok_session_files(grok_home, cutoff)
            self.assertEqual([found for _, found in files], [path])

            meta, stats, entries, skills = parse_grok_session(path, {"update-skill"}, False)

            self.assertEqual(meta["id"], "abc-123")
            self.assertEqual(meta["cwd"], "/tmp/repo")
            self.assertEqual(meta["originator"], "grok")
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 2)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["error_outputs"], 0)
            self.assertTrue(stats["has_code_edits"])
            self.assertEqual(skills, ["update-skill"])
            self.assertEqual(entries[0], ("user", "Fix the collector"))
            self.assertNotIn("system-reminder", json.dumps(entries))


class ZcodeSessionTests(unittest.TestCase):
    def test_parses_last_request_messages_and_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-io-sess_1.jsonl"
            empty_request = {"request": {"body": {"messages": []}}}
            full_request = {
                "request": {
                    "body": {
                        "messages": [
                            {"role": "system", "content": "You are ZCode."},
                            {"role": "user", "content": "Update the skill"},
                            {
                                "role": "assistant",
                                "content": "Checking.",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": (
                                                '{"path": "/r/.agents/skills/'
                                                'update-skill/SKILL.md"}'
                                            ),
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "content": "skill body"},
                        ]
                    }
                }
            }
            path.write_text(json.dumps(empty_request) + "\n" + json.dumps(full_request) + "\n")

            meta, stats, entries, skills = parse_zcode_session(path, {"update-skill"}, False)

            self.assertEqual(meta["id"], "sess_1")
            self.assertEqual(meta["originator"], "zcode")
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 1)
            self.assertEqual(skills, ["update-skill"])
            self.assertEqual(entries[0], ("user", "Update the skill"))

    def test_returns_none_without_request_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-io-sess_2.jsonl"
            path.write_text('{"unrelated": true}\n')

            self.assertIsNone(parse_zcode_session(path, set(), False))


if __name__ == "__main__":
    unittest.main()
