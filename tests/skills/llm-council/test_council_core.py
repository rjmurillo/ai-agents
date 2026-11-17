"""Tests for council_core: ranking parse, Borda count, members, and prompts.

Ported from the machine-config llm-council unittest suite (parse_ranking,
borda, routing), plus prompt and artifact checks for the shared module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

core = import_skill_script(
    ".claude/skills/llm-council/scripts/council_core.py", module_name="council_core"
)

L3 = ["Response A", "Response B", "Response C"]
L4 = [*L3, "Response D"]


# parse_ranking


@pytest.mark.parametrize(
    ("text", "labels", "expected"),
    [
        (
            "Prose.\n\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response B",
            L3,
            ["Response C", "Response A", "Response B"],
        ),
        (
            "Prose\n\n**FINAL RANKING:**\n1. **Response B**\n2. **Response A**\n3. **Response C**",
            L3,
            ["Response B", "Response A", "Response C"],
        ),
        ("## FINAL RANKING:\n1) Response A\n2) Response B\n3) Response C\n", L3, L3),
        (
            "FINAL RANKING:\n1. Response A\n(slight edge on rigor)\n2. Response B\n3. Response C\n",
            L3,
            L3,
        ),
        ("FINAL RANKING:\n\n1. Response A\n\n2. Response B\n\n3. Response C\n", L3, L3),
        ("final ranking:\n1. Response A\n2. Response B\n3. Response C", L3, L3),
        (
            "FINAL RANKING:\n1. Response D\n2. Response A\n3. Response C\n4. Response B",
            L4,
            ["Response D", "Response A", "Response C", "Response B"],
        ),
    ],
    ids=[
        "plain",
        "bolded",
        "heading",
        "trailing-prose",
        "blank-lines",
        "case-insensitive",
        "four-labels",
    ],
)
def test_parse_ranking_accepts(text, labels, expected):
    assert core.parse_ranking(text, labels) == expected


@pytest.mark.parametrize(
    "text",
    [
        "FINAL RANKING:\n1. Response A\n2. Response B",
        "just prose",
        "FINAL RANKING:\n1. Response A\n2. Response A\n3. Response B",
        "FINAL RANKING:\n1. Response A\n2. Response E\n3. Response B",
    ],
    ids=["incomplete", "no-marker", "duplicate", "unknown-label"],
)
def test_parse_ranking_rejects(text):
    assert core.parse_ranking(text, L3) is None


# borda


def test_borda_simple_tie():
    rankings = {
        "m1": ["Response A", "Response B", "Response C"],
        "m2": ["Response B", "Response A", "Response C"],
    }

    scores = dict(core.borda(rankings, L3))

    assert scores == pytest.approx({"Response A": 1.5, "Response B": 1.5, "Response C": 3.0})


def test_borda_consensus_winner():
    rankings = {m: ["Response A", "Response B"] for m in ("m1", "m2", "m3")}

    result = core.borda(rankings, ["Response A", "Response B"])

    assert result[0] == ("Response A", pytest.approx(1.0))


def test_borda_label_with_no_votes_gets_sentinel():
    scores = dict(core.borda({"m1": ["Response A"]}, ["Response A", "Response B"]))

    assert scores["Response B"] == 99


# Members


def test_copilot_model_recognition():
    for model in ("claude-opus-5.5", "gpt-6-astra", "gpt-6-sol", "claude-sonnet-5"):
        assert core.is_copilot_model(model)
    for model in ("openai/gpt-4.1", "meta/llama-3.3-70b-instruct", "deepseek/deepseek-v3-0324"):
        assert not core.is_copilot_model(model)


def test_task_shaped_frontier_defaults_are_unchanged():
    expected = {"claude-opus-5.5", "gpt-6-astra", "gpt-6-sol", "claude-sonnet-5"}
    for mode, models in core.COUNCILS_BY_MODE.items():
        assert set(models) == expected, mode
        assert len(models) == 4, mode
    assert core.CHAIRMEN_BY_MODE["general"] == "gpt-6-astra"
    assert core.CHAIRMEN_BY_MODE["research"] == "claude-opus-5.5"


@pytest.mark.parametrize(
    ("mode", "models", "cheap", "chairman", "expected"),
    [
        ("plan", None, False, None, (core.COUNCILS_BY_MODE["plan"], "gpt-6-astra")),
        ("review", None, False, None, (core.COUNCILS_BY_MODE["review"], "claude-opus-5.5")),
        ("general", None, True, None, (core.CHEAP_COUNCIL, core.CHEAP_CHAIRMAN)),
        ("general", " a, b ,", False, "c", (["a", "b"], "c")),
    ],
)
def test_resolve_members(mode, models, cheap, chairman, expected):
    assert core.resolve_members(mode, models, cheap, chairman) == expected


# Prompts and artifact


def test_safe_substitute_does_not_reinject_placeholders():
    out = core.safe_substitute("{a} {b}", {"{a}": "{b}", "{b}": "B"})

    assert out == "{b} B"


def test_ranker_prompt_is_anonymised():
    prompt = core.ranker_prompt(
        "Q?", ["gpt-6-sol", "claude-opus-5.5"], {"gpt-6-sol": "one", "claude-opus-5.5": "two"}
    )

    assert "Response A:\none" in prompt
    assert "Response B:\ntwo" in prompt
    assert "gpt-6-sol" not in prompt


@pytest.mark.parametrize("mode", core.MODES)
def test_chairman_prompt_has_question_and_both_stages(mode):
    prompt = core.chairman_prompt(mode, "Q?", ["m1"], {"m1": "answer"}, {"m1": "ranking"})

    assert prompt.startswith("You are the Chairman")
    assert "QUESTION:\nQ?" in prompt
    assert "Model: m1\nResponse: answer" in prompt
    assert "Model: m1\nRanking: ranking" in prompt


def test_general_chairman_prompt_keeps_attribution_label():
    assert "with model attribution" in core.chairman_template("general")


def test_render_artifact_sections():
    run = {
        "mode": "design",
        "chairman": "gpt-6-astra",
        "council": ["m1", "m2"],
        "errors": {"m2": "timeout"},
        "question": "Q?",
        "synthesis": "Verdict.",
        "survivors": ["m1"],
        "responses": {"m1": "answer"},
        "aggregate": [("Response A", 1.0)],
        "label_map": {"Response A": "m1"},
        "rankings_raw": {"m1": "FINAL RANKING:\n1. Response A"},
    }

    md = core.render_artifact(run)

    for part in (
        "# LLM Council: design mode",
        "**Errors:** `m2`: timeout",
        "## Chairman Synthesis\n\nVerdict.",
        "- 1.0: `m1`",
        "### Response A: `m1`",
        "### Ranker `m1`",
    ):
        assert part in md
