"""The linter's limits and grammars mirror the host repository's gates.

lint_skill_frontmatter.py is stdlib-only and cannot import the host validators, so
it carries copies of their constants. This test reads both sides and fails when
they differ, which keeps a change to one from drifting away from the other.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

from tests.skills.skillforge.conformance_support import load

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_capability_graph
import check_skill_artifact_flow
import check_skill_trigger_resolution
import skill_size

_SKILLS = _REPO_ROOT / "src" / "claude" / "skills"
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
    'Plan work. Use when you say `plan this`, "break it down". Do NOT use for `build this`.',
    "Use when you say `design this schema`. Then `run tool.py` and `/slash cmd` text.",
    'Only `quoted` single words and "more" quotes.',
    'Duplicates: `ship it`, "ship it", and `ship   it`.',
    "No quotes at all.",
)


@pytest.mark.parametrize("description", _DESCRIPTIONS, ids=range(len(_DESCRIPTIONS)))
def test_trigger_phrase_extraction_matches_the_resolution_gate(description: str) -> None:
    mine = lint.trigger_phrases(description)
    theirs = tuple(check_skill_trigger_resolution.extract_phrases(description))

    assert mine == theirs


def test_trigger_phrase_extraction_matches_the_gate_on_every_shipped_description() -> None:
    descriptions = [
        _description(path) for path in sorted(_SKILLS.glob("*/SKILL.md")) if _description(path)
    ]

    mismatches = [
        text
        for text in descriptions
        if lint.trigger_phrases(text) != tuple(check_skill_trigger_resolution.extract_phrases(text))
    ]

    assert len(descriptions) > 100
    assert mismatches == []


def _description(path: Path) -> str:
    match = re.match(r"---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.DOTALL)
    if match is None:
        return ""
    front = yaml.safe_load(match.group(1)) or {}
    value = front.get("description")
    return value if isinstance(value, str) else ""
