#!/usr/bin/env python3
"""Tests for skill-doctor session collection."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_sessions import (
    detect_skills_from_entries,
    discover_skills,
    find_claude_session_files,
    parse_claude_session,
    session_matches_repos,
)
from session_test_helpers import (
    write_jsonl,
)


class ClaudeSessionTests(unittest.TestCase):
    def test_discovers_skills_and_matches_sessions_across_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first_skill = first / ".agents" / "skills" / "alpha" / "SKILL.md"
            second_skill = second / ".claude" / "skills" / "beta" / "SKILL.md"
            first_skill.parent.mkdir(parents=True)
            second_skill.parent.mkdir(parents=True)
            first_skill.write_text("---\ndescription: Alpha\n---\n")
            second_skill.write_text("---\ndescription: Beta\n---\n")

            skills = discover_skills(
                [first, second],
                root / "codex-home",
                [first_skill.parent.parent],
                False,
            )

            self.assertEqual(set(skills), {"alpha", "beta"})
            automatic = discover_skills([first, second], root / "codex-home", [], False)
            self.assertEqual(set(automatic), {"beta"})
            self.assertTrue(session_matches_repos(second / "src", [first, second]))
            self.assertFalse(session_matches_repos(root / "elsewhere", [first, second]))

    def test_discovers_global_skills_without_repositories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            homes = {
                name: root / f"{name}-home" for name in ("codex", "pi", "grok", "zcode", "hermes")
            }
            for name, home in homes.items():
                skill = home / "skills" / f"{name}-skill" / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(f"---\ndescription: {name.title()} skill\n---\n")

            skills = discover_skills(
                [],
                homes["codex"],
                [],
                True,
                pi_home=homes["pi"],
                grok_home=homes["grok"],
                zcode_home=homes["zcode"],
                hermes_home=homes["hermes"],
            )

            self.assertTrue(
                {
                    "codex-skill",
                    "pi-skill",
                    "grok-skill",
                    "zcode-skill",
                    "hermes-skill",
                }.issubset(skills)
            )

    def test_detects_skills_from_deferred_tool_entries(self):
        entries = [
            ("tool:Skill", '{"skill": "alpha"}'),
            ("tool:read", '{"path": "/repo/.agents/skills/beta/SKILL.md"}'),
            ("assistant", "Mentioning gamma here does not count."),
        ]

        self.assertEqual(
            detect_skills_from_entries(entries, {"alpha", "beta", "gamma"}),
            {"alpha", "beta"},
        )

    def test_discovers_parent_sessions_and_optional_subagents(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp)
            parent = claude_home / "projects" / "-repo" / "parent.jsonl"
            subagent = (
                claude_home / "projects" / "-repo" / "parent" / "subagents" / "agent-child.jsonl"
            )
            old = claude_home / "projects" / "-repo" / "old.jsonl"
            for path in (parent, subagent, old):
                write_jsonl(path, [{"type": "user"}])
            old_time = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
            os.utime(old, (old_time, old_time))
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

            parents = find_claude_session_files(claude_home, cutoff, False)
            with_subagents = find_claude_session_files(claude_home, cutoff, True)

            self.assertEqual([path for _, path in parents], [parent])
            self.assertEqual(
                {path for _, path in with_subagents},
                {parent, subagent},
            )

    def test_parses_messages_tools_skills_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            common = {
                "sessionId": "session-1",
                "cwd": "/tmp/repo",
                "timestamp": "2026-08-20T10:00:00Z",
                "version": "1.0.0",
            }
            write_jsonl(
                path,
                [
                    {
                        **common,
                        "type": "user",
                        "uuid": "user-1",
                        "message": {"role": "user", "content": "Improve my skill"},
                    },
                    {
                        **common,
                        "type": "assistant",
                        "uuid": "assistant-1",
                        "message": {
                            "id": "message-1",
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "I will inspect it."},
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "update-skill"},
                                },
                            ],
                        },
                    },
                    {
                        **common,
                        "type": "assistant",
                        "uuid": "assistant-2",
                        "message": {
                            "id": "message-1",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Edit",
                                    "input": {"file_path": "/tmp/repo/SKILL.md"},
                                }
                            ],
                        },
                    },
                    {
                        **common,
                        "type": "user",
                        "uuid": "result-1",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "is_error": True,
                                    "content": "permission denied",
                                }
                            ],
                        },
                    },
                ],
            )

            meta, stats, entries, skills = parse_claude_session(
                path,
                {"update-skill"},
                False,
            )

            self.assertEqual(meta["id"], "session-1")
            self.assertEqual(meta["cwd"], "/tmp/repo")
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["error_outputs"], 1)
            self.assertTrue(stats["has_code_edits"])
            self.assertEqual(skills, ["update-skill"])
            self.assertIn(("user", "Improve my skill"), entries)
            self.assertIn(("assistant", "I will inspect it."), entries)

    def test_excludes_sidechains_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-child.jsonl"
            write_jsonl(
                path,
                [
                    {
                        "type": "user",
                        "sessionId": "session-1",
                        "agentId": "child-1",
                        "isSidechain": True,
                        "cwd": "/tmp/repo",
                        "timestamp": "2026-08-20T10:00:00Z",
                        "message": {"role": "user", "content": "Investigate"},
                    }
                ],
            )

            self.assertIsNone(parse_claude_session(path, set(), False))
            parsed = parse_claude_session(path, set(), True)
            self.assertEqual(parsed[0]["id"], "session-1-child-1")
            self.assertEqual(parsed[0]["thread_source"], "subagent")


if __name__ == "__main__":
    unittest.main()


def _session(key, skills):
    return {"_key": key, "skills_used": skills}


def test_sample_counts_every_skill_a_multi_skill_session_used():
    from types import SimpleNamespace

    from session_sampling import sample_one_harness

    sessions = [_session("ab", ["a", "b"]), _session("b", ["b"]), _session("c", ["c"])]
    args = SimpleNamespace(max_sessions=2, per_skill=1, no_skill=0)

    sampled = sample_one_harness(sessions, {"a": {}, "b": {}, "c": {}}, args)

    assert sampled == {"ab", "c"}


def test_sample_still_takes_a_session_when_any_used_skill_has_quota():
    from types import SimpleNamespace

    from session_sampling import sample_one_harness

    sessions = [_session("a", ["a"]), _session("ab", ["a", "b"])]
    args = SimpleNamespace(max_sessions=5, per_skill=1, no_skill=0)

    sampled = sample_one_harness(sessions, {"a": {}, "b": {}}, args)

    assert sampled == {"a", "ab"}
