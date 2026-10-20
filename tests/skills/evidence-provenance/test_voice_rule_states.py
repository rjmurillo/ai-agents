"""The voice rule names only check states that the evidence-provenance skill accepts.

`classify_lineage` exits 1 as `named-without-state` for any state label outside
`STATES`, so a voice rule that asks for another label cannot compose with it
(follow-up to #6686).
"""

from __future__ import annotations

import re
from pathlib import Path

import classify_lineage

REPO_ROOT = Path(__file__).resolve().parents[3]
VOICE_RULE = REPO_ROOT / "templates" / "rules" / "voice.md"
STARTED_UNREAD = "A started check you have not read"
_STATE_TOKEN = re.compile(r"`([A-Z][A-Z ]+)`")


def _sentence(text: str, start: str) -> str:
    """Return the sentence of `text` that begins with `start`."""
    begin = text.index(start)
    return text[begin : text.index(". ", begin) + 1]


def _foreign_states(sentence: str) -> list[str]:
    """Backticked uppercase labels in `sentence` that the skill does not accept."""
    return [t for t in _STATE_TOKEN.findall(sentence) if t not in classify_lineage.STATES]


def test_started_unread_check_maps_to_a_skill_state() -> None:
    sentence = _sentence(VOICE_RULE.read_text(encoding="utf-8"), STARTED_UNREAD)
    assert "`UNAVAILABLE`" in sentence
    assert _foreign_states(sentence) == []


def test_the_state_list_in_the_rule_matches_the_skill() -> None:
    text = VOICE_RULE.read_text(encoding="utf-8")
    sentence = _sentence(text, "Name check states as the `evidence-provenance` skill does")
    named = tuple(_STATE_TOKEN.findall(sentence))
    assert named == classify_lineage.STATES


def test_a_label_outside_the_skill_states_is_detected() -> None:
    assert _foreign_states("A started check is `UNREAD`, not `NOT RUN`.") == ["UNREAD"]
    assert _foreign_states("A started check is `UNAVAILABLE`, not `NOT RUN`.") == []
