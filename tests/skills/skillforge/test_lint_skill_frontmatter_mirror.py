"""The linter's limits and grammars mirror the host repository's gates.

lint_skill_frontmatter.py is stdlib-only and cannot import the host validators, so
it carries copies of their constants. This test reads both sides and fails when
they differ, which keeps a change to one from drifting away from the other.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.skills.skillforge.conformance_support import load

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_capability_graph
import check_skill_artifact_flow
import skill_routing_resolver_evidence
import skill_size

lint = load("skillforge_frontmatter_lint_mirror_under_test", "lint_skill_frontmatter.py")


def test_artifact_name_grammar_matches_the_flow_gate() -> None:
    assert lint.ARTIFACT_RE.pattern == check_skill_artifact_flow.ARTIFACT_RE.pattern


def test_artifact_path_grammar_matches_the_flow_gate() -> None:
    assert lint.PATH_RE.pattern == check_skill_artifact_flow.PATH_RE.pattern


def test_handoff_grammar_matches_the_flow_gate() -> None:
    assert lint.HANDOFF_RE.pattern == check_skill_artifact_flow.HANDOFF_RE.pattern


def test_input_sources_match_the_flow_gate() -> None:
    assert lint.SOURCES == check_skill_artifact_flow.SOURCES


def test_input_option_keys_match_the_flow_gate() -> None:
    assert lint.INPUT_KEYS == check_skill_artifact_flow.INPUT_KEYS


def test_output_option_keys_match_the_flow_gate() -> None:
    assert lint.OUTPUT_KEYS == check_skill_artifact_flow.OUTPUT_KEYS


def test_capability_kinds_match_the_graph_gate() -> None:
    assert lint.CAPABILITY_KINDS == check_capability_graph.KINDS


def test_capability_keys_match_the_graph_gate() -> None:
    assert set(lint.CAPABILITY_KEYS) == set(check_capability_graph.BLOCK_KEYS)


def test_skill_byte_limit_matches_the_size_gate() -> None:
    assert lint.SKILL_BYTE_LIMIT == skill_size.SKILL_BYTE_LIMIT


_DESCRIPTIONS = (
    'Plan work. Use when you say `plan this`, "break it down". Do NOT use for builds.',
    "Use when you say `design this schema`. Then more text with `not a phrase` in it.",
    'No lead-in here, only `quoted` text and "more" quotes.',
    "USE WHEN YOU SAY `a. b` and `c`. Trailing `ignored`.",
    'Use   when\nyou say\n`spaced   out`,  "two  words" . After.',
)


@pytest.mark.parametrize("description", _DESCRIPTIONS, ids=range(len(_DESCRIPTIONS)))
def test_trigger_phrase_extraction_matches_the_routing_evidence_gate(description: str) -> None:
    mine = lint.trigger_phrases(description)
    theirs = skill_routing_resolver_evidence.trigger_phrases(description)

    assert mine == theirs


def test_trigger_phrase_samples_exercise_both_none_and_tuple_results() -> None:
    results = [lint.trigger_phrases(text) for text in _DESCRIPTIONS]

    assert None in results
    assert any(isinstance(result, tuple) and result for result in results)
