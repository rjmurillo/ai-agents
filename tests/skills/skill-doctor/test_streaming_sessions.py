#!/usr/bin/env python3
"""Tests for skill-doctor session collection."""

import tempfile
import unittest
from pathlib import Path

from collect_sessions import (
    parse_claude_session,
    parse_codex_session,
)
from session_test_helpers import (
    write_jsonl,
    write_jsonl_past_previous_limit,
)


class StreamingSessionReadTests(unittest.TestCase):
    def test_claude_and_codex_parse_records_after_previous_file_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_path = root / "claude.jsonl"
            codex_path = root / "codex.jsonl"
            write_jsonl_past_previous_limit(
                claude_path,
                {
                    "type": "user",
                    "sessionId": "claude-session",
                    "cwd": "/tmp/repo",
                    "timestamp": "2026-08-30T10:00:00Z",
                    "message": {"role": "user", "content": "hello"},
                },
                [
                    {
                        "type": "assistant",
                        "sessionId": "claude-session",
                        "cwd": "/tmp/repo",
                        "timestamp": "2026-08-30T10:01:00Z",
                        "message": {
                            "id": "late-message",
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "late claude message"},
                                {
                                    "type": "tool_use",
                                    "name": "Read",
                                    "input": {
                                        "file_path": "/tmp/.agents/skills/late-skill/SKILL.md"
                                    },
                                },
                            ],
                        },
                    }
                ],
            )
            write_jsonl_past_previous_limit(
                codex_path,
                {
                    "type": "session_meta",
                    "payload": {"id": "codex-session", "cwd": "/tmp/repo"},
                },
                [
                    {
                        "type": "response_item",
                        "timestamp": "2026-08-30T10:00:30Z",
                        "payload": {
                            "type": "function_call",
                            "name": "read_file",
                            "arguments": {
                                "path": "/tmp/.codex/skills/late-skill/SKILL.md",
                                "operation": "apply_patch",
                            },
                        },
                    },
                    {
                        "type": "response_item",
                        "timestamp": "2026-08-30T10:01:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": "late codex message"}],
                        },
                    },
                ],
            )

            parsed_claude = parse_claude_session(claude_path, {"late-skill"}, False)
            parsed_codex = parse_codex_session(codex_path, {"late-skill"}, False)

            self.assertEqual(parsed_claude[1]["assistant_turns"], 1)
            self.assertEqual(parsed_claude[1]["tool_calls"], 1)
            self.assertEqual(parsed_claude[3], ["late-skill"])
            self.assertIn(("assistant", "late claude message"), parsed_claude[2])
            self.assertEqual(parsed_codex[1]["tool_calls"], 1)
            self.assertTrue(parsed_codex[1]["has_code_edits"])
            self.assertEqual(parsed_codex[3], ["late-skill"])
            self.assertIn(("assistant", "late codex message"), parsed_codex[2])

    def test_codex_keeps_only_transcript_head_and_tail_while_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codex.jsonl"
            records = [
                {
                    "type": "session_meta",
                    "payload": {"id": "codex-session", "cwd": "/tmp/repo"},
                }
            ]
            for index in range(201):
                records.extend(
                    (
                        {
                            "type": "event_msg",
                            "payload": {"type": "agent_message"},
                        },
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "text", "text": f"message-{index}"}],
                            },
                        },
                    )
                )
            write_jsonl(path, records)

            _, stats, entries, _ = parse_codex_session(path, set(), False)

            self.assertEqual(stats["assistant_turns"], 201)
            self.assertEqual(len(entries), 141)
            self.assertEqual(entries[0], ("assistant", "message-0"))
            self.assertEqual(entries[99], ("assistant", "message-99"))
            self.assertEqual(entries[100], ("note", "[... 61 entries omitted ...]"))
            self.assertEqual(entries[101], ("assistant", "message-161"))
            self.assertEqual(entries[-1], ("assistant", "message-200"))


if __name__ == "__main__":
    unittest.main()
