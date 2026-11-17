"""Tests for the sol-loop finding rules: reply parsing, drop reasons, overlap."""

from __future__ import annotations

import pytest

from tests.skills.claude_skills_import import import_skill_script

rules = import_skill_script(
    ".claude/skills/sol-loop/scripts/sol_findings.py", module_name="sol_loop_findings_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)


def _finding(**overrides):
    base = {
        "id": "S1",
        "severity": "should",
        "file": "src/app/b.py",
        "line": 5,
        "claim": "KeyError on empty input",
        "repro": "pytest tests/test_b.py::test_empty fails with KeyError",
        "fix": "guard the empty case",
    }
    base.update(overrides)
    return base


# Reply parsing


def test_parses_verdict_and_full_finding_line():
    reply = (
        "VERDICT: CHANGES\n"
        "S1 [blocker] src/app/b.py:42 drops the timeout. "
        "Repro: run `x --timeout 1` and it hangs. Fix: pass timeout.\n"
    )

    verdict, findings = rules.parse_reply(reply)

    assert verdict == "CHANGES"
    assert findings == [
        {
            "id": "S1",
            "severity": "blocker",
            "file": "src/app/b.py",
            "line": 42,
            "claim": "drops the timeout",
            "repro": "run `x --timeout 1` and it hangs",
            "fix": "pass timeout.",
        }
    ]


@pytest.mark.parametrize(
    "verdict_line",
    ["VERDICT: APPROVE", "**VERDICT:** APPROVE", "verdict: approve", "  VERDICT : APPROVE"],
)
def test_verdict_line_variants(verdict_line):
    assert rules.parse_reply(verdict_line + "\n")[0] == "APPROVE"


def test_reply_without_verdict_raises():
    with pytest.raises(rules.ReplyError):
        rules.parse_reply("S1 [should] a.py:1 bug. Repro: x.\n")


def test_parses_backticked_location_and_bullets():
    reply = (
        "VERDICT: CHANGES\n- **S2** [Should] `pkg/mod.py:7` wrong sign. Repro: f(-1) returns 1.\n"
    )

    _, findings = rules.parse_reply(reply)

    assert (
        findings[0]["id"],
        findings[0]["severity"],
        findings[0]["file"],
        findings[0]["line"],
    ) == (
        "S2",
        "should",
        "pkg/mod.py",
        7,
    )
    assert findings[0]["repro"] == "f(-1) returns 1"


def test_finding_without_location_parses_with_empty_file():
    _, findings = rules.parse_reply(
        "VERDICT: CHANGES\nS3 [should] the cache never expires. Repro: wait.\n"
    )

    assert (findings[0]["file"], findings[0]["line"]) == ("", None)


def test_prose_lines_are_not_findings():
    _, findings = rules.parse_reply("VERDICT: APPROVE\nLooks fine overall.\nNo S-ids here.\n")

    assert findings == []


# Drop reasons


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"severity": "nit"}, "nit"),
        ({"severity": "style"}, "unknown-severity"),
        ({"severity": ""}, "unknown-severity"),
        ({"severity": "p1"}, "unknown-severity"),
        ({"file": ""}, "missing-file"),
        ({"file": None}, "missing-file"),
        ({"line": None}, "missing-line"),
        ({"line": 0}, "missing-line"),
        ({"line": "12"}, "missing-line"),
        ({"line": True}, "missing-line"),
        ({"repro": ""}, "missing-repro"),
        ({"repro": "   "}, "missing-repro"),
    ],
)
def test_drops_nits_and_incomplete_findings(override, reason):
    kept, dropped = rules.filter_findings([_finding(**override)])

    assert kept == []
    assert dropped[0]["reason"] == reason


def test_drops_non_object_findings():
    kept, dropped = rules.filter_findings(["S1 a.py:1 bad"])

    assert (kept, dropped[0]["reason"]) == ([], "not-an-object")


@pytest.mark.parametrize("severity", ["blocker", "should", "BLOCKER"])
def test_keeps_complete_blocker_or_should(severity):
    kept, dropped = rules.filter_findings([_finding(severity=severity)])

    assert dropped == []
    assert kept[0]["file"] == "src/app/b.py"


def test_parsed_reply_drops_missing_repro_end_to_end():
    _, findings = rules.parse_reply(
        "VERDICT: CHANGES\nS1 [should] a.py:3 off by one. Fix: use <=.\n"
    )

    kept, dropped = rules.filter_findings(findings)

    assert (kept, dropped[0]["reason"]) == ([], "missing-repro")


# Overlap with the critic


@pytest.mark.parametrize(
    ("critic", "file", "line", "sol_only"),
    [
        ("src/app/a.py:10", "src/app/a.py", 13, False),
        ("src/app/a.py:10", "src/app/a.py", 14, True),
        ("foo.py:10-40", "foo.py", 30, False),
        ("foo.py:10-40", "foo.py", 44, True),
        ("see app/a.py:10", "a.py", 10, False),
        ("./src/x.py:5", "src/x.py", 5, False),
        (".claude/x.py:5", "claude/x.py", 5, True),
        ("src/other.py:10", "src/app/a.py", 10, True),
    ],
)
def test_overlap_rule(critic, file, line, sol_only):
    marked = rules.mark_sol_only([_finding(file=file, line=line)], critic)

    assert marked[0]["sol_only"] is sol_only


def test_overlap_against_realistic_critic_text():
    marked = rules.mark_sol_only([_finding(file="src/app/a.py", line=11), _finding()], CRITIC_TEXT)

    assert [f["sol_only"] for f in marked] == [False, True]


@pytest.mark.parametrize("label", ["P1", "P2", "major", "High"])
def test_non_brief_severity_is_parsed_then_dropped_by_name(label):
    _, findings = rules.parse_reply(f"VERDICT: CHANGES\nS1 [{label}] a.py:3 bug. Repro: run x.\n")

    kept, dropped = rules.filter_findings(findings)

    assert (len(findings), kept) == (1, [])
    assert dropped[0]["reason"] == "unknown-severity"


@pytest.mark.parametrize("prefix", ["1. ", "2) ", "- ", "* "])
def test_list_markers_before_the_id_are_accepted(prefix):
    _, findings = rules.parse_reply(
        f"VERDICT: CHANGES\n{prefix}S1 [should] a.py:3 bug. Repro: run x.\n"
    )

    assert [(f["id"], f["file"], f["line"]) for f in findings] == [("S1", "a.py", 3)]


# Location forms seen in real replies and critic reports


def test_markdown_link_location_uses_the_link_target():
    reply = (
        "VERDICT: CHANGES\n"
        "S1 [should] [sol_loop.py:124](/repo/src/sol_loop.py:124) strips the status. "
        "Repro: modify a tracked file. Fix: keep the space.\n"
    )

    _, findings = rules.parse_reply(reply)

    assert (findings[0]["file"], findings[0]["line"]) == ("/repo/src/sol_loop.py", 124)
    assert findings[0]["claim"] == "strips the status"
    assert findings[0]["repro"] == "modify a tracked file"


def test_markdown_link_without_line_in_target_falls_back_to_label():
    _, findings = rules.parse_reply("VERDICT: CHANGES\nS1 [should] [a.py:9](a.py) bug. Repro: x.\n")

    assert (findings[0]["file"], findings[0]["line"]) == ("a.py", 9)


def test_hash_line_location():
    _, findings = rules.parse_reply("VERDICT: CHANGES\nS1 [should] src/a.py#L7 bug. Repro: x.\n")

    assert (findings[0]["file"], findings[0]["line"]) == ("src/a.py", 7)


@pytest.mark.parametrize(
    ("critic", "file", "line"),
    [
        ("Makefile:10 has a bad target", "Makefile", 10),
        ("see `a.py`:12 for the bug", "a.py", 12),
        ("see a.py#L12", "a.py", 12),
        ("see a.py#L10-L20", "a.py", 18),
    ],
)
def test_critic_location_forms_count_as_overlap(critic, file, line):
    marked = rules.mark_sol_only([_finding(file=file, line=line)], critic)

    assert marked[0]["sol_only"] is False


def test_absolute_sol_path_overlaps_relative_critic_path():
    marked = rules.mark_sol_only([_finding(file="/repo/src/app/a.py", line=10)], CRITIC_TEXT)

    assert marked[0]["sol_only"] is False


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("[f.py:12](/abs/f.py:12:5)", ("/abs/f.py", 12)),
        ("[f.py:12](/abs/f.py:12)", ("/abs/f.py", 12)),
        ("[f.py#L12](/abs/f.py#L12-L20)", ("/abs/f.py", 12)),
    ],
)
def test_link_target_with_column_keeps_the_line(location, expected):
    # Regression for the round 2 critic D1: a column must not become the line.
    _, findings = rules.parse_reply(f"VERDICT: CHANGES\nS1 [should] {location} bug. Repro: x.\n")

    assert (findings[0]["file"], findings[0]["line"]) == expected
