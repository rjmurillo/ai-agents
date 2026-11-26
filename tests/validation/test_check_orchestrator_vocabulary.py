"""Guards for the router-vocabulary lint (ADR-065 Decision 1, issue #7639).

Coverage:

- positive: router framing passes; ``management`` and tool names in the
  frontmatter tool list pass; a token inside a fence or an inline code span
  passes; the real repository tree passes in all three rendered trees.
- negative: each ADR-065 token family fails in the body and in the
  description, including verb forms, ``manager``, ``supervisor``, and
  ``notice when`` across a space run.
- edge: a long fence is not closed by a short one; a missing router file and
  unreadable frontmatter fail; the scope is the ``DELEGATORS`` set from
  ``check_agent_delegation.py``; CLI exit codes 0, 1, and 2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_agent_delegation
import check_orchestrator_vocabulary as gate

_CLEAN_DESCRIPTION = "Routes work, sequences handoffs, and synthesizes results."


def _text(body: str, description: str = _CLEAN_DESCRIPTION, extra: str = "") -> str:
    return f"---\nname: orchestrator\ndescription: {description}\n{extra}---\n\n{body}\n"


def _line_of(text: str, word: str) -> int:
    """Return the 1-based file line holding ``word``, the number a reader jumps to."""
    return next(
        n for n, line in enumerate(text.splitlines(), 1) if word in line and ":" not in line
    )


def _root(tmp_path: Path, text: str) -> Path:
    for tree, suffix in gate.AGENT_TREES:
        folder = tmp_path / tree
        folder.mkdir(parents=True)
        for name in gate.DELEGATORS:
            (folder / f"{name}{suffix}").write_text(text, encoding="utf-8")
    return tmp_path


class TestScanPasses:
    def test_router_framing(self) -> None:
        assert gate.scan_text(_text("Classify, route, retry, and synthesize.")) == []

    def test_management_noun_is_allowed(self) -> None:
        assert gate.scan_text(_text("## Context Budget Management\n\nKeep the window small.")) == []

    def test_tool_list_is_not_prose(self) -> None:
        extra = "tools:\n  - cloudmcp-manager/*\n"
        assert gate.scan_text(_text("Route the task.", extra=extra)) == []

    def test_fenced_token_is_not_prose(self) -> None:
        assert gate.scan_text(_text("```text\nsupervise the worker\n```\nRoute it.")) == []

    def test_inline_code_is_not_prose(self) -> None:
        assert gate.scan_text(_text("Call `cloudmcp-manager/search` to look up memory.")) == []


class TestScanFails:
    @pytest.mark.parametrize(
        "word",
        [
            "manage",
            "managing",
            "manager",
            "supervise",
            "supervisor",
            "coach",
            "coaching",
            "mentor",
            "course-correct",
            "course correct",
            "notice  when",
            "motivate",
            "oversee",
            "oversaw",
        ],
    )
    def test_body_token(self, word: str) -> None:
        text = _text(f"Intro.\n\nYou {word} the specialists.")
        token = " ".join(word.split())
        assert gate.scan_text(text) == [f"line {_line_of(text, word)}: '{token}'"]

    def test_description_token(self) -> None:
        findings = gate.scan_text(_text("Route it.", description="Routes work, managing handoffs."))
        assert findings == ["description: 'managing'"]

    def test_token_after_a_closed_fence_counts(self) -> None:
        text = _text("```\ncode\n```\nYou coach the worker.")
        assert gate.scan_text(text) == [f"line {_line_of(text, 'coach')}: 'coach'"]

    def test_long_fence_is_not_closed_by_a_short_one(self) -> None:
        body = "````\n```\nsupervise\n````\nRoute it."
        assert gate.scan_text(_text(body)) == []

    def test_phrase_wrapped_across_lines_is_caught(self) -> None:
        text = _text("If you notice\nwhen a worker is stuck, interrupt it.")
        assert gate.scan_text(text) == [f"line {_line_of(text, 'If you notice')}: 'notice when'"]

    def test_hit_on_a_later_paragraph_line_reports_that_line(self) -> None:
        text = _text("Route the task.\nThen coach the worker.")
        assert gate.scan_text(text) == [f"line {_line_of(text, 'Then coach')}: 'coach'"]

    def test_code_span_wrapped_across_lines_is_not_prose(self) -> None:
        assert gate.scan_text(_text("Call `cloudmcp-\nmanager/search` for memory.")) == []

    def test_blank_line_ends_a_paragraph(self) -> None:
        assert gate.scan_text(_text("If you notice\n\nwhen a worker is stuck, route.")) == []

    def test_fence_with_inner_info_string_stays_open(self) -> None:
        body = "```markdown\n```python\nsupervise\n```\nRoute it."
        assert gate.scan_text(_text(body)) == []

    def test_non_ascii_space_after_a_fence_does_not_close_it(self) -> None:
        body = "```text\n```\u00a0\nsupervise\n```\nRoute it."
        assert gate.scan_text(_text(body)) == []

    def test_tab_after_a_fence_still_closes_it(self) -> None:
        text = _text("```text\ncode\n```\t\nYou coach them.")
        assert gate.scan_text(text) == [f"line {_line_of(text, 'You coach')}: 'coach'"]

    def test_unclosed_fence_is_a_finding(self) -> None:
        findings = gate.scan_text(_text("Route it.\n```text\nYou supervise the worker."))
        assert findings == [
            "a fenced code block never closes, so the rest of the body went unscanned"
        ]

    def test_non_string_description_is_a_finding(self) -> None:
        text = "---\nname: orchestrator\ndescription: [a, list]\n---\n\nRoute it.\n"
        assert gate.scan_text(text) == ["description is not a string (list)"]

    def test_backticks_are_the_only_escape(self) -> None:
        assert gate.scan_text(_text("Never `supervise` a worker.")) == []
        assert gate.scan_text(_text("Never supervise a worker.")) != []

    def test_missing_frontmatter_raises(self) -> None:
        with pytest.raises(ValueError, match="frontmatter"):
            gate.scan_text("You manage the team.\n")


class TestTree:
    def test_scope_is_the_delegator_registry(self) -> None:
        assert gate.DELEGATORS is check_agent_delegation.DELEGATORS

    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        assert gate.find_vocabulary_findings(_root(tmp_path, _text("Route it."))) == []

    def test_dirty_tree_reports_every_rendered_copy(self, tmp_path: Path) -> None:
        findings = gate.find_vocabulary_findings(_root(tmp_path, _text("You manage them.")))
        assert len(findings) == len(gate.AGENT_TREES) * len(gate.DELEGATORS)

    def test_missing_router_file_fails(self, tmp_path: Path) -> None:
        root = _root(tmp_path, _text("Route it."))
        tree, suffix = gate.AGENT_TREES[1]
        (root / tree / f"orchestrator{suffix}").unlink()
        findings = gate.find_vocabulary_findings(root)
        assert findings == [
            (f"{tree.as_posix()}/orchestrator{suffix}", "router agent file is missing")
        ]

    def test_unreadable_file_fails(self, tmp_path: Path) -> None:
        root = _root(tmp_path, "no frontmatter\n")
        findings = gate.find_vocabulary_findings(root)
        assert findings and all("cannot scan" in text for _, text in findings)


class TestEntryPoints:
    def test_clean_exit_zero(self, tmp_path: Path) -> None:
        assert gate.main([str(_root(tmp_path, _text("Route it.")))]) == 0

    def test_dirty_exit_one_names_the_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert gate.main([str(_root(tmp_path, _text("You coach them.")))]) == 1
        assert "src/claude/agents/orchestrator.md: line 6: 'coach'" in capsys.readouterr().err

    def test_missing_claude_tree_exit_two(self, tmp_path: Path) -> None:
        assert gate.main([str(tmp_path)]) == 2

    def test_invalid_root_exit_two(self, tmp_path: Path) -> None:
        assert gate.main([str(tmp_path / "absent")]) == 2


class TestRealTree:
    def test_repository_router_agents_are_clean(self) -> None:
        assert gate.find_vocabulary_findings(REPO_ROOT) == []
