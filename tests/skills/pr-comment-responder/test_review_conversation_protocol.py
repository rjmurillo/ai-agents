"""Contract tests for the review-conversation protocol (issue #5403)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_PROTOCOL = (
    _ROOT / ".claude" / "skills" / "pr-comment-responder" / "references" / "review-conversation.md"
)
_OWNER = ".claude/skills/pr-comment-responder/SKILL.md"
_OWNER_LINK = "(references/review-conversation.md)"
_ANCHORED = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
    "/skills/pr-comment-responder/references/review-conversation.md"
)
_CONSUMERS = [
    ".claude/skills/pr-review/SKILL.md",
    ".claude/skills/review/resources/technical-review.md",
    ".claude/agents/pr-comment-responder.md",
]


def _text() -> str:
    return _PROTOCOL.read_text(encoding="utf-8")


def test_protocol_exists_and_has_no_dashes() -> None:
    text = _text()
    assert "—" not in text
    assert "–" not in text


@pytest.mark.parametrize("disposition", ["BLOCKING", "OPTIONAL", "NIT", "FYI"])
def test_protocol_defines_each_disposition(disposition: str) -> None:
    assert f"`{disposition}`" in _text()


def test_protocol_defers_prefixes_to_review_norms() -> None:
    assert "`code-review-norms`" in _text()
    assert (_ROOT / ".agents" / "governance" / "code-review-norms.md").is_file()


def test_protocol_forbids_severity_mutation() -> None:
    text = _text()
    assert "never changes the finding's" in text
    assert "technical severity" in text


def test_scenario_checklist_covers_all_eighteen() -> None:
    section = _text().split("## Scenario checklist", 1)[1]
    numbers = re.findall(r"^(\d+)\. ", section, flags=re.MULTILINE)
    assert numbers == [str(n) for n in range(1, 19)]


def test_protocol_states_round_count_survives_handoff() -> None:
    text = _text()
    assert "check_pr_round_cap.py" in text
    assert "never restarts it" in text


@pytest.mark.parametrize("consumer", _CONSUMERS)
def test_consumer_anchors_pointer_to_plugin_root(consumer: str) -> None:
    assert _ANCHORED in (_ROOT / consumer).read_text(encoding="utf-8")


def test_owner_links_protocol_relative_to_its_own_directory() -> None:
    assert _OWNER_LINK in (_ROOT / _OWNER).read_text(encoding="utf-8")


@pytest.mark.parametrize("consumer", [*_CONSUMERS, _OWNER])
def test_consumer_does_not_copy_protocol_table(consumer: str) -> None:
    body = (_ROOT / consumer).read_text(encoding="utf-8")
    assert "Dispositions and their comment prefixes come from" not in body
    assert "An AI author is neither a compliance bot" not in body
