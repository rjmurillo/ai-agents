"""CodeRabbit pass 6: the twelve findings that reproduced at 6430c1af14.

Each test names its pass-6 item number. Every one failed before its fix.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import adr_commits
import adr_docs
import adr_log
import adr_reason
import adr_shape
import pytest

F3 = "`" * 3
_SKILL = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-bootstrap"


def _ids(text: str) -> list[str | None]:
    return [entry.id for entry in adr_log.split_decision_log(text)]


def _is_bot(author: object) -> bool | None:
    verdict: bool | None = adr_commits._is_bot({"author": author})
    return verdict


# --- 1: a bump inside release notes no longer hides the author's reason ---


def test_1_a_bump_inside_release_notes_keeps_the_author_reason() -> None:
    reason = "Pin the parser because the old one crashes on CRLF input."
    body = f"{reason}\n\n## Release notes\nBumps parser from 1.2.0 to 1.3.0."

    assert adr_reason.extract_reason("Pin the parser", body) == reason


def test_1_a_bump_body_with_no_author_text_still_has_no_reason() -> None:
    assert adr_reason.extract_reason("Bump parser", "Bumps parser from 1.2.0 to 1.3.0.") is None


# --- 5: GitHub's SSH endpoint on port 443 ---


def test_5_the_ssh_github_com_endpoint_maps_to_github() -> None:
    assert adr_commits.web_base("ssh://git@ssh.github.com:443/o/r.git") == (
        "github",
        "https://github.com/o/r",
    )


def test_5_other_hosts_are_unchanged() -> None:
    assert adr_commits.web_base("git@github.com:o/r.git") == ("github", "https://github.com/o/r")
    assert adr_commits.web_base("https://gitlab.example.com/a/b") == (
        "gitlab",
        "https://gitlab.example.com/a/b",
    )


# --- 7: a release title that states a rule ---


def test_7_a_release_title_that_states_a_rule_is_not_housekeeping() -> None:
    assert not adr_shape.is_release_or_bump_subject("Release 2.4 should not ship on Fridays")


@pytest.mark.parametrize("subject", ["Release 2.4", "Released 5.11.2 with the fixes below"])
def test_7_a_plain_release_title_stays_housekeeping(subject: str) -> None:
    assert adr_shape.is_release_or_bump_subject(subject)


# --- 8 and 9: bot detection ---


def test_8_a_non_bool_is_bot_makes_the_row_incomplete() -> None:
    assert _is_bot({"login": "ci-helper", "is_bot": "true"}) is None


def test_8_a_bool_or_absent_is_bot_still_decides() -> None:
    assert _is_bot({"login": "ci-helper", "is_bot": True}) is True
    assert _is_bot({"login": "ci-helper"}) is False


def test_8_select_prs_counts_a_non_bool_is_bot_as_incomplete() -> None:
    item: dict[str, Any] = {
        "number": 12,
        "title": "Adopt X for parsing",
        "body": "We adopt X because Y is slow.",
        "url": "https://github.com/o/r/pull/12",
        "mergedAt": "2026-01-02T00:00:00Z",
        "author": {"login": "ci-helper", "is_bot": "yes"},
    }
    dropped: dict[str, int] = {}

    assert adr_commits.select_prs([item], dropped, "https://github.com/o/r") == []
    assert dropped.get("pr_incomplete") == 1


def test_9_a_human_login_with_a_bot_prefix_is_not_a_bot() -> None:
    assert _is_bot({"login": "renovate-maintainer"}) is False


@pytest.mark.parametrize(
    "login", ["renovate", "Renovate", "renovate[bot]", "dependabot[bot]", "dependabot-preview[bot]"]
)
def test_9_real_bot_accounts_are_bots(login: str) -> None:
    assert _is_bot({"login": login}) is True


# --- 12: inline code of any backtick length ---


def test_12_a_because_inside_triple_backtick_code_does_not_score() -> None:
    body = f"Run {F3}a because b{F3} in a shell to check the flag."

    assert adr_reason.extract_reason("Adopt X for parsing", body) is None


# --- 13: a pull request path compares without regard to case ---


def test_13_an_uppercase_pull_segment_has_the_same_identity() -> None:
    upper = adr_docs._url_identity("https://github.com/o/r/PULL/12")

    assert upper == adr_docs._url_identity("https://github.com/o/r/pull/12")


# --- 20 and 22: changelog policy headings ---


def test_20_a_policy_heading_with_a_later_date_is_kept() -> None:
    assert adr_docs.is_rule_section("changelog", "Versioning policy since 2024-01", "x")


@pytest.mark.parametrize("heading", ["2026-07-07", "[1.2.0] - 2026-01-01", "Unreleased"])
def test_20_a_dated_release_entry_is_still_not_policy(heading: str) -> None:
    assert not adr_docs.is_rule_section("changelog", heading, "x")


def test_22_a_versioned_release_heading_is_not_changelog_policy() -> None:
    assert not adr_docs.is_rule_section("changelog", "Release 2.0 deprecation", "x")


# --- 23: a marker indented four spaces past the opener stays inside the fence ---


def test_23_a_four_space_marker_inside_a_top_level_fence_stays_text() -> None:
    assert _ids(f"{F3}\n    {F3}\n## D-2 Example only\n{F3}\n") == []


def test_23_a_fence_inside_a_list_item_still_closes_at_its_own_indent() -> None:
    text = (
        "## D-1 Adopt x\nbecause y and z\n- example:\n"
        f"  {F3}\n  ## D-9 not a heading\n  {F3}\n## D-2 Adopt w\nbecause q and r\n"
    )

    assert _ids(text) == ["D-1", "D-2"]


# --- 31: HTML comments hide a breaking footer ---


def test_31_a_breaking_footer_inside_an_html_comment_is_ignored() -> None:
    body = "Body.\n\n<!-- note\n\nBREAKING CHANGE: describe the break -->"

    assert not adr_reason.breaking_change("feat: x", body)


def test_31_a_footer_after_a_closed_comment_still_counts() -> None:
    body = "Body.\n\n<!-- a --> x <!-- b\nstill hidden\n-->\nBREAKING CHANGE: after"

    assert adr_reason.breaking_change("feat: x", body)


# --- 37: the exit-3 payload rule matches the handlers ---


def test_37_the_reference_names_io_for_every_script_that_prints_io_on_exit_3() -> None:
    doc = (_SKILL / "references" / "scripts.md").read_text(encoding="utf-8")
    io_on_3 = re.compile(r'"error": "io".*\n\s+return 3')
    for script in sorted((_SKILL / "scripts").glob("bootstrap_*.py")):
        if io_on_3.search(script.read_text(encoding="utf-8")):
            assert f"`{script.name}`" in doc.split("for exit 3.", 1)[1].split("\n", 1)[0]
    assert "`git` or `io` for exit 3" in doc
