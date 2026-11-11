"""Tests for scripts/agent_pr_intervention_metrics.py and its CLI wiring."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from scripts import agent_pr_intervention_metrics as m
from tests.agent_pr_intervention_helpers import (
    BOT,
    HUMAN,
    NOW,
    OWNER,
    OWNER_NAME,
    _actor,
    _pr,
    _thread,
)

# ---------------------------------------------------------------------------
# Agent-author detection
# ---------------------------------------------------------------------------


class TestIsAgentPr:
    def test_trailer_on_owner_pr_marks_agent_pr(self) -> None:
        assert m.is_agent_pr(_pr(author=OWNER), OWNER_NAME)

    def test_owner_login_match_is_case_insensitive(self) -> None:
        assert m.is_agent_pr(_pr(author=_actor("RJMurillo")), OWNER_NAME)

    def test_trailer_on_a_stranger_pr_is_not_trusted(self) -> None:
        # Anyone can type the trailer; only the owner's PRs may use it.
        assert not m.is_agent_pr(_pr(author=_actor("mallory")), OWNER_NAME)

    def test_no_trailer_and_human_author_is_not_agent(self) -> None:
        assert not m.is_agent_pr(_pr(body="Plain description.", author=HUMAN), OWNER_NAME)

    def test_owner_pr_without_trailer_is_not_agent(self) -> None:
        assert not m.is_agent_pr(_pr(body="Plain description.", author=OWNER), OWNER_NAME)

    def test_coding_agent_author_without_trailer_is_agent(self) -> None:
        coding_agent = _actor("copilot-swe-agent", "Bot", 198982749)
        assert m.is_agent_pr(_pr(body="Plain.", author=coding_agent), OWNER_NAME)

    def test_repository_bot_user_account_is_agent(self) -> None:
        assert m.is_agent_pr(_pr(body="Plain.", author=_actor("rjmurillo-bot")), OWNER_NAME)

    def test_dependency_bot_is_not_agent(self) -> None:
        pr = _pr(body="Bump x.", author=_actor("renovate", "Bot"))
        assert not m.is_agent_pr(pr, OWNER_NAME)

    def test_null_body_and_null_author_is_not_agent(self) -> None:
        pr = _pr(body="")
        pr["body"] = None
        pr["author"] = None
        assert not m.is_agent_pr(pr, OWNER_NAME)


# ---------------------------------------------------------------------------
# Intervention counting
# ---------------------------------------------------------------------------


class TestCountInterventions:
    def test_bot_opened_thread_is_ignored(self) -> None:
        assert m.count_interventions(_pr(threads=[_thread(BOT), _thread(BOT)])) == 0

    def test_human_opened_thread_counts_once(self) -> None:
        assert m.count_interventions(_pr(threads=[_thread(HUMAN), _thread(BOT)])) == 1

    def test_owner_reply_in_bot_thread_is_not_counted(self) -> None:
        # The agent replies as the owner; only the first comment decides, and the
        # query requests only that comment, so replies are not even fetched.
        assert m.count_interventions(_pr(threads=[_thread(BOT)])) == 0

    def test_approval_with_no_comment_is_not_an_intervention(self) -> None:
        review = {"state": "APPROVED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_human_changes_requested_counts(self) -> None:
        review = {"state": "CHANGES_REQUESTED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 1

    def test_bot_changes_requested_is_ignored(self) -> None:
        review = {"state": "CHANGES_REQUESTED", "author": BOT}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_commented_review_from_human_is_not_counted(self) -> None:
        review = {"state": "COMMENTED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_user_typed_account_listed_in_bot_authors_is_a_bot(self) -> None:
        listed = _actor("rjmurillo-bot")
        assert m.count_interventions(_pr(threads=[_thread(listed)])) == 0

    def test_login_suffix_alone_does_not_make_a_bot(self) -> None:
        # Any person can pick a name ending in -bot, so it must count as human.
        lookalike = _actor("alice-bot")
        assert m.count_interventions(_pr(threads=[_thread(lookalike)])) == 1

    def test_human_named_like_a_listed_app_is_not_a_bot(self) -> None:
        # bot-authors.yml lists cursor[bot]; a person named cursor is not that app.
        person = _actor("cursor")
        app = _actor("cursor", "Bot")
        assert m.count_interventions(_pr(threads=[_thread(person)])) == 1
        assert m.count_interventions(_pr(threads=[_thread(app)])) == 0

    def test_review_and_threads_each_count(self) -> None:
        review = {"state": "CHANGES_REQUESTED", "author": HUMAN}
        pr = _pr(threads=[_thread(HUMAN), _thread(HUMAN)], reviews=[review])
        assert m.count_interventions(pr) == 3

    def test_deleted_account_thread_counts_as_human(self) -> None:
        thread = {"comments": {"nodes": [{"author": None}]}}
        assert m.count_interventions(_pr(threads=[thread])) == 1

    def test_empty_thread_is_skipped(self) -> None:
        assert m.count_interventions(_pr(threads=[{"comments": {"nodes": []}}])) == 0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestBuildMetrics:
    def _build(self, prs: list[dict[str, Any]]) -> m.InterventionMetrics:
        return m.build_metrics(prs, NOW - timedelta(days=30), NOW, OWNER_NAME)

    def test_splits_merged_unmerged_and_open(self) -> None:
        prs = [
            _pr(1),
            _pr(2, state="CLOSED", merged=False),
            _pr(3, state="OPEN", merged=False),
        ]
        result = self._build(prs)
        assert {k: c.prs for k, c in result.cohorts.items()} == {
            m.MERGED: 1,
            m.UNMERGED: 1,
            m.OPEN: 1,
        }

    def test_zero_rate_and_counts(self) -> None:
        prs = [
            _pr(1),
            _pr(2, threads=[_thread(HUMAN)]),
            _pr(3, threads=[_thread(HUMAN), _thread(HUMAN), _thread(HUMAN)]),
            _pr(4),
        ]
        merged = self._build(prs).cohorts[m.MERGED]
        assert merged.prs == 4
        assert merged.zero_touch == 2
        assert merged.zero_rate == 0.5
        assert merged.interventions == 4
        assert merged.median_when_intervened == 2

    def test_human_authored_prs_are_discarded(self) -> None:
        prs = [_pr(1, body="Plain.", author=HUMAN, threads=[_thread(HUMAN)])]
        assert self._build(prs).total_prs == 0

    def test_pr_older_than_window_is_excluded(self) -> None:
        assert self._build([_pr(1, days_old=31)]).total_prs == 0

    def test_empty_cohort_has_no_rate(self) -> None:
        result = self._build([])
        assert result.cohorts[m.MERGED].zero_rate is None
        assert result.cohorts[m.MERGED].median_when_intervened is None

    def test_zero_touch_sample_lists_only_merged_zero_intervention_prs(self) -> None:
        prs = [
            _pr(1),
            _pr(2, threads=[_thread(HUMAN)]),
            _pr(3, state="CLOSED", merged=False),
        ]
        assert [p["number"] for p in self._build(prs).zero_touch_merged] == [1]

    def test_status_of_each_state(self) -> None:
        assert m.pr_status(_pr(state="MERGED", merged=True)) == m.MERGED
        assert m.pr_status(_pr(state="CLOSED", merged=False)) == m.UNMERGED
        assert m.pr_status(_pr(state="OPEN", merged=False)) == m.OPEN


class TestRender:
    def test_report_has_table_sample_and_definitions(self) -> None:
        prs = [_pr(n) for n in range(1, 4)]
        metrics = m.build_metrics(prs, NOW - timedelta(days=30), NOW, OWNER_NAME)
        text = m.render_report(metrics, NOW)
        assert "| merged | 3 | 3 | 100.0% | 0 | n/a |" in text
        assert "[#3](https://github.com/o/r/pull/3): `PR 3`" in text
        assert "## Definitions" in text
        assert "2026-10-11 to 2026-11-10" in text
        assert not any(ch in text for ch in (chr(0x2014), chr(0x2013)))

    def test_sample_is_capped_and_spread(self) -> None:
        prs = [_pr(n) for n in range(1, 41)]
        metrics = m.build_metrics(prs, NOW - timedelta(days=30), NOW, OWNER_NAME)
        text = m.render_report(metrics, NOW)
        assert text.count("- [#") == m.ZERO_TOUCH_SAMPLE_SIZE
        assert "10 of 40 merged PRs" in text
        sampled = [int(n) for n in re.findall(r"- \[#(\d+)\]", text)]
        assert sampled == sorted(sampled, reverse=True)
        assert sampled[0] == 40 and sampled[-1] <= 4  # spans the whole list

    def test_empty_sample_prints_none(self) -> None:
        metrics = m.build_metrics([], NOW - timedelta(days=30), NOW, OWNER_NAME)
        assert "- none" in m.render_report(metrics, NOW)

    def test_title_is_an_inert_code_span(self) -> None:
        hostile = "\\[x\\](https://evil.example) <img src=x> `tick`\nnext"
        rendered = m._inert_title(hostile)
        assert rendered.startswith("`") and rendered.endswith("`")
        assert rendered.count("`") == 2
        assert "\n" not in rendered

    def test_title_drops_control_and_format_characters(self) -> None:
        hostile = "a\u202eb\u200bc\x1b[31md\x00e"
        rendered = m._inert_title(hostile)
        assert rendered == "`abc[31mde`"

    def test_long_title_is_capped(self) -> None:
        rendered = m._inert_title("a" * 500)
        assert len(rendered) == m.TITLE_MAX_CHARS + 2
        assert rendered.endswith("...`")


class TestWriteReport:
    def test_creates_parent_and_leaves_no_temp_file(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "report.md"
        m.write_report(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"
        assert [p.name for p in target.parent.iterdir()] == ["report.md"]
