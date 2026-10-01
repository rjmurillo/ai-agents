"""Contract tests for the review-conversation protocol (issue #5403)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_PROTOCOL = (
    _ROOT / ".claude" / "skills" / "pr-comment-responder" / "references" / "review-conversation.md"
)
_POINTER = "references/review-conversation.md"
_CONSUMERS = [
    ".claude/skills/pr-comment-responder/SKILL.md",
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
    assert ".agents/governance/code-review-norms.md" in _text()
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
def test_consumer_points_to_protocol(consumer: str) -> None:
    assert _POINTER in (_ROOT / consumer).read_text(encoding="utf-8")


@pytest.mark.parametrize("consumer", _CONSUMERS)
def test_consumer_does_not_copy_protocol_table(consumer: str) -> None:
    body = (_ROOT / consumer).read_text(encoding="utf-8")
    assert "Dispositions and their comment prefixes come from" not in body
    assert "An AI author is neither a compliance bot" not in body
