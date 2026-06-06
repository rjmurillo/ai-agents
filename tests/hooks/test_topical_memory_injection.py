"""Tests for the PreToolUse invoke_topical_memory_injection hook (issue #2005).

Covers topic keying from the file path, the filesystem memory scan (ranking,
top-3, topic matching), the 2KB advisory cap, and the main() contract (advisory
on match, silent exit-0 on no match / missing memories / bad input).
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

from invoke_topical_memory_injection import (  # noqa: E402
    MAX_INJECT_BYTES,
    derive_topic,
    find_topical_memories,
    main,
    parse_file_path,
    relativize,
    render_advisory,
)


class TestDeriveTopic:
    def test_skill_path_uses_skill_name(self):
        assert derive_topic(".claude/skills/github/scripts/pr/foo.py") == "github"

    def test_hooks_path(self):
        assert derive_topic(".claude/hooks/PreToolUse/bar.py") == "hooks"

    def test_validation_path(self):
        assert derive_topic("scripts/validation/pre_pr.py") == "validation"

    def test_scripts_path(self):
        assert derive_topic("scripts/sync_plugin_lib.py") == "scripts"

    def test_templates_path(self):
        assert derive_topic("templates/agents/security.shared.md") == "templates"

    def test_fallback_first_segment(self):
        assert derive_topic("docs/retros/INDEX.md") == "docs"

    def test_topic_is_sanitized(self):
        # No traversal / glob metacharacters survive into the topic key.
        assert ".." not in (derive_topic(".claude/skills/../etc/x.py") or "")


class TestRelativize:
    def test_under_root(self):
        assert relativize("/repo/.claude/hooks/x.py", "/repo") == ".claude/hooks/x.py"

    def test_already_relative(self):
        assert relativize("scripts/x.py", "/repo") == "scripts/x.py"


class TestParseFilePath:
    def test_extracts_file_path(self):
        data = json.dumps({"tool_input": {"file_path": "/repo/a.py"}})
        assert parse_file_path(data) == "/repo/a.py"

    def test_missing_is_none(self):
        assert parse_file_path(json.dumps({"tool_input": {}})) is None

    def test_bad_json_is_none(self):
        assert parse_file_path("{not json") is None


class TestRenderAdvisory:
    def test_format(self):
        out = render_advisory("github", [("github/pr-ops.md", "PR ops")])
        assert "Topical memory (github)" in out
        assert ".serena/memories/github/pr-ops.md - PR ops" in out

    def test_caps_at_2kb(self):
        many = [(f"github/m{i}.md", "x" * 500) for i in range(20)]
        out = render_advisory("github", many)
        assert len(out.encode("utf-8")) <= MAX_INJECT_BYTES + 32
        assert "truncated" in out


def _stdin_for(tmp_path: Path, rel: str = ".claude/skills/github/x.py") -> str:
    return json.dumps({"tool_input": {"file_path": str(tmp_path / rel)}})


def _seed_memories(tmp_path: Path, files: dict[str, str]) -> None:
    mem = tmp_path / ".serena" / "memories"
    for rel, content in files.items():
        p = mem / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class TestFindTopicalMemories:
    def test_matches_topic_in_path(self, tmp_path):
        _seed_memories(tmp_path, {
            "github/github-cli-pr-operations.md": "# PR ops\nbody",
            "powershell/powershell-array-handling.md": "# arrays\nbody",
        })
        out = find_topical_memories(str(tmp_path), "github", time.monotonic() + 10)
        assert len(out) == 1
        assert out[0][0] == "github/github-cli-pr-operations.md"
        assert out[0][1] == "PR ops"

    def test_top_3_by_mtime(self, tmp_path):
        _seed_memories(tmp_path, {f"hooks/git-hooks-{i}.md": f"# h{i}\n" for i in range(5)})
        # bump mtimes so ordering is deterministic
        mem = tmp_path / ".serena" / "memories" / "hooks"
        for i, p in enumerate(sorted(mem.glob("*.md"))):
            os.utime(p, (1000 + i, 1000 + i))
        out = find_topical_memories(str(tmp_path), "hooks", time.monotonic() + 10)
        assert len(out) == 3

    def test_missing_dir_returns_empty(self, tmp_path):
        assert find_topical_memories(str(tmp_path), "github", time.monotonic() + 10) == []

    def test_summary_skips_frontmatter(self, tmp_path):
        # A memory file with YAML frontmatter must summarize to the heading,
        # not the first frontmatter key (e.g. "status: accepted").
        _seed_memories(tmp_path, {
            "github/github-cli-notes.md": "---\nstatus: accepted\ntags: [a, b]\n---\n# Real Heading\nbody",
        })
        out = find_topical_memories(str(tmp_path), "github", time.monotonic() + 10)
        assert len(out) == 1
        assert out[0][1] == "Real Heading"

    def test_summary_skips_frontmatter_after_leading_blank(self, tmp_path):
        # A blank line before the opening --- must not defeat frontmatter skip.
        _seed_memories(tmp_path, {
            "github/github-cli-blank.md": "\n\n---\nstatus: accepted\n---\n# Real Heading\nbody",
        })
        out = find_topical_memories(str(tmp_path), "github", time.monotonic() + 10)
        assert len(out) == 1
        assert out[0][1] == "Real Heading"

    def test_respects_budget_when_deadline_passed(self, tmp_path, monkeypatch):
        # The summary loop is bounded by the deadline: once the budget is spent
        # it stops reading files and returns the subset summarized so far. With
        # the deadline already passed when the summary loop begins, it returns
        # an empty list rather than raising. Matches are mtime-sorted, so any
        # entries that do fit the budget are the freshest. (Bugbot R7i: the
        # break is a deliberate ~80ms budget bound for this advisory hook.)
        _seed_memories(tmp_path, {"github/github-cli-pr-operations.md": "# PR ops\nbody"})
        import invoke_topical_memory_injection as mod
        calls = {"n": 0}

        def fake_monotonic():
            calls["n"] += 1
            return 50.0 if calls["n"] == 1 else 150.0

        monkeypatch.setattr(mod.time, "monotonic", fake_monotonic)
        out = mod.find_topical_memories(str(tmp_path), "github", 100.0)
        assert out == []


class TestMain:
    def _run(self, tmp_path, stdin: str, monkeypatch, capsys):
        (tmp_path / ".agents").mkdir(exist_ok=True)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        with patch.object(sys, "stdin", io.StringIO(stdin)):
            with patch.object(sys.stdin, "isatty", return_value=False):
                rc = main()
        return rc, capsys.readouterr()

    def test_advisory_on_match(self, tmp_path, monkeypatch, capsys):
        _seed_memories(tmp_path, {"github/github-cli-pr-operations.md": "# PR ops\n"})
        stdin = _stdin_for(tmp_path)
        rc, cap = self._run(tmp_path, stdin, monkeypatch, capsys)
        assert rc == 0
        assert "Topical memory (github)" in cap.out
        # Regression #2468: stdout MUST be the valid PreToolUse advisory
        # envelope (hookSpecificOutput.additionalContext), not a top-level
        # decision:"allow", which Claude Code rejects and silently drops.
        payload = json.loads(cap.out)
        assert "decision" not in payload
        assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert (
            "Topical memory (github)"
            in payload["hookSpecificOutput"]["additionalContext"]
        )

    def test_silent_when_no_match(self, tmp_path, monkeypatch, capsys):
        _seed_memories(tmp_path, {"powershell/x.md": "# x\n"})
        stdin = _stdin_for(tmp_path)
        rc, cap = self._run(tmp_path, stdin, monkeypatch, capsys)
        assert rc == 0
        assert cap.out.strip() == ""

    def test_silent_when_no_memories_dir(self, tmp_path, monkeypatch, capsys):
        stdin = _stdin_for(tmp_path)
        rc, cap = self._run(tmp_path, stdin, monkeypatch, capsys)
        assert rc == 0
        assert cap.out.strip() == ""

    def test_bad_stdin_exits_zero(self, tmp_path, monkeypatch, capsys):
        rc, _ = self._run(tmp_path, "{not json", monkeypatch, capsys)
        assert rc == 0

    def test_consumer_repo_skips(self, tmp_path, monkeypatch, capsys):
        # No .agents/ -> skip_if_consumer_repo returns True -> silent exit 0.
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        stdin = json.dumps({"tool_input": {"file_path": "/x/.claude/skills/github/x.py"}})
        with patch.object(sys, "stdin", io.StringIO(stdin)):
            with patch.object(sys.stdin, "isatty", return_value=False):
                rc = main()
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""
