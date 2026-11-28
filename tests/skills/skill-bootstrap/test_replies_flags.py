"""Flag heuristics and transcript parsing units. Each test pairs a positive with a negative."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from replies_helpers import (
    api_error,
    assistant_text,
    assistant_tool,
    replies_corpus,
    replies_flags,
    tool_result,
    user,
    write_child,
    write_session,
)

flags = replies_flags


@pytest.mark.parametrize(
    ("flag", "positive", "negative"),
    [
        ("offer_tail", "All done. Want me to continue?", "All done. Merged and verified."),
        ("ends_question", "Which branch should win?", "Branch main wins."),
        ("decision_head", "## Facts for your decision\nA or B", "## Result\nA shipped"),
        ("self_chore", "The branch is 3 commits behind main.", "The branch is current."),
        (
            "bare_ids3",
            "See ADR-001 and ADR-002 and ADR-003 and #1234 today.",
            "See ADR-001 (log), ADR-002 (index), ADR-003 (rules), #1234: fix.",
        ),
    ],
)
def test_agent_flag_positive_and_negative(flag: str, positive: str, negative: str) -> None:
    assert flag in flags.agent_flags(positive)
    assert flag not in flags.agent_flags(negative)


def test_long_reply_flags_depend_on_lead() -> None:
    body = "x" * 1600
    assert {"long1500", "long_no_lead"} <= set(flags.agent_flags(body))
    assert "long_no_lead" not in flags.agent_flags("Result: shipped.\n" + body)
    assert "long4000" in flags.agent_flags("y" * 4100)
    assert "long1500" not in flags.agent_flags("short")


@pytest.mark.parametrize(
    ("flag", "positive", "negative"),
    [
        ("swear", "this is bullshit", "this is fine"),
        ("confused", "I'm confused, what do you want", "thanks, clear"),
        ("repeat", "I already told you this", "first time asking"),
        ("ownjob", "rebase it and rerun", "looks good"),
        ("wrong_claim", "that's wrong, it isn't merged", "that matches"),
        ("neg_start", "no, stop", "yes please"),
        ("short_question", "why is that?", "this is a statement"),
    ],
)
def test_human_flag_positive_and_negative(flag: str, positive: str, negative: str) -> None:
    assert flag in flags.human_flags(positive, 0)
    assert flag not in flags.human_flags(negative, 0)


def test_short_after_long_needs_a_long_reply() -> None:
    assert "short_after_long" in flags.human_flags("ok then", 2000)
    assert "short_after_long" not in flags.human_flags("ok then", 100)


@pytest.mark.parametrize("text", ["continue", "Keep going.", "status?", "??", "go"])
def test_bare_nudges_are_generic_not_authority(text: str) -> None:
    found = flags.human_flags(text, 0)
    assert "generic_nudge" in found and "prior_authority" not in found


@pytest.mark.parametrize(
    "text",
    [
        "you already have my approval",
        "I authorized this earlier",
        "this is a full send",
        "as agreed, merge it",
    ],
)
def test_authority_references_are_not_nudges(text: str) -> None:
    found = flags.human_flags(text, 0)
    assert "prior_authority" in found and "generic_nudge" not in found
    assert "prior_authority" not in flags.human_flags("please look at the failing test", 0)


def test_authority_with_continue_stays_authority() -> None:
    assert "prior_authority" in flags.human_flags("you have my approval, continue", 0)


def test_fingerprint_and_eval_marker() -> None:
    long_a = "Please build the synthetic widget exporter with tests and docs for the suite"
    assert flags.prompt_fingerprint(long_a) == flags.prompt_fingerprint(
        "  " + long_a.upper() + "\n"
    )
    assert flags.prompt_fingerprint("too short") is None
    assert flags.prompt_fingerprint(long_a) != flags.prompt_fingerprint(long_a + " extra")
    assert flags.is_eval_marked("[eval] case 1") and flags.is_eval_marked("eval_run 3")
    assert not flags.is_eval_marked("evaluate the widget")


def test_parse_ts_handles_zulu_naive_and_garbage() -> None:
    zulu = replies_corpus.parse_ts("2026-11-01T00:00:00Z")
    naive = replies_corpus.parse_ts("2026-11-01T00:00:00")
    assert zulu is not None and zulu == naive
    assert replies_corpus.parse_ts("nope") is None and replies_corpus.parse_ts(None) is None


def parse(tmp_path: Path, records: list[dict[str, Any]]) -> replies_corpus.Transcript:
    path = write_session(tmp_path / "p", "s1", records)
    return replies_corpus.parse_transcript(replies_corpus.Source(path, "s1", None, False))


def test_sidechain_records_skipped_in_main_but_kept_in_child(tmp_path: Path) -> None:
    recs = [
        user("hello wording tau", 1),
        assistant_text("side text", 2, isSidechain=True),
        assistant_text("main text", 3),
    ]
    main = parse(tmp_path, recs)
    assert [t.text for t in main.turns if t.role == "reply"] == ["main text"]
    child_path = write_child(tmp_path / "p", "s1", "agent-1", recs[1:2])
    child = replies_corpus.parse_transcript(
        replies_corpus.Source(child_path, "agent-1", "s1", True)
    )
    assert [t.text for t in child.turns if t.role == "reply"] == ["side text"]


def test_interrupt_discards_pending_reply(tmp_path: Path) -> None:
    recs = [
        user("hello wording upsilon", 1),
        assistant_text("partial", 2),
        user("[Request interrupted by user]", 3),
    ]
    turns = parse(tmp_path, recs).turns
    assert [t.role for t in turns] == ["human", "interrupt"]


def test_text_before_tool_is_not_a_reply_and_error_spans_are_typed(tmp_path: Path) -> None:
    recs = [user("hello wording phi", 1), assistant_tool(2, narration="narration"), tool_result(3)]
    recs += [user("next typed message wording", 4), assistant_tool(5), api_error(6)]
    turns = parse(tmp_path, recs).turns
    assert [t.role for t in turns] == ["human", "human", "error"]
    assert turns[-1].reason == "api"
    assert not any(t.role == "reply" for t in turns)


def test_comma_list_counts_every_bare_id_and_glosses_still_pass() -> None:
    assert flags.bare_ids("See ADR-001, ADR-002, ADR-003 today.") == 3
    assert "bare_ids3" in flags.agent_flags("See ADR-001, ADR-002, ADR-003 today.")
    assert flags.bare_ids("See ADR-001 (log), ADR-002 (index), #1234: fix.") == 0
    assert flags.bare_ids("See [ADR-001] and ADR-002: rules.") == 0


def test_fingerprint_does_not_raise_on_a_lone_surrogate() -> None:
    text = "Please build the synthetic widget exporter \ud800 with tests and docs"
    assert flags.prompt_fingerprint(text) == flags.prompt_fingerprint(text.upper())
    assert flags.prompt_fingerprint(text) != flags.prompt_fingerprint(text + " extra")
    assert flags.prompt_fingerprint("\ud800") is None


def test_recursion_error_line_counts_as_a_bad_line(tmp_path: Path) -> None:
    recs = [user("hello wording omega", 1), assistant_text("main text", 2)]
    path = write_session(tmp_path / "p", "s1", recs)
    deep = '{"type": "user", "x": ' + "[" * 200000 + "]" * 200000 + "}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(deep)
    parsed = replies_corpus.parse_transcript(replies_corpus.Source(path, "s1", None, False))
    assert parsed.parse_errors == 1
    assert [t.text for t in parsed.turns if t.role == "reply"] == ["main text"]


def test_leading_reminder_block_is_notice_only_when_nothing_typed_follows(
    tmp_path: Path,
) -> None:
    block = "<system-reminder>synthetic reminder body</system-reminder>"
    recs = [
        user(block, 1),
        user(block + "\nplease fix the typed part", 2),
        user("Caveat: synthetic notice", 3),
        user(block + "\nCaveat: synthetic notice after a block", 4),
        assistant_text("main text", 5),
    ]
    parsed = parse(tmp_path, recs)
    assert dict(parsed.skipped) == {"notice": 3}
    humans = [t.text for t in parsed.turns if t.role == "human"]
    assert humans == ["please fix the typed part"]
