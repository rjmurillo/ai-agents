"""Rule ``stale-as-of``: an as-of date older than a date the diff added nearby."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.doc_date_drift_helpers import commit_head, drift, make_repo, rules, where

SKILL = "templates/skills/quota.SKILL.md.tmpl"


def _skill(bullet_date: str, as_of: str = "rechecked on 2026-06-01") -> str:
    return f"# Quota\n\n- Limit is 100 requests ({bullet_date}).\n- {as_of}\n"


class TestMoqAnalyzers1495Shape:
    def test_bumping_a_bullet_date_next_to_an_old_recheck_is_flagged(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-06-01")})
        commit_head(root, {SKILL: _skill("2026-11-01")})
        (finding,) = drift(root)
        assert finding.rule == "stale-as-of"
        assert where(finding) == (SKILL, 4)
        assert (finding.other_path, finding.other_line) == (SKILL, 3)
        assert finding.suggested == "2026-11-01"

    def test_the_as_of_line_need_not_be_added(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-06-01")})
        commit_head(root, {SKILL: _skill("2026-11-01")})
        assert [where(f) for f in drift(root)] == [(SKILL, 4)]

    def test_an_added_as_of_older_than_an_added_neighbour_is_flagged(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {SKILL: _skill("2026-11-01")})
        assert rules(drift(root)) == {"stale-as-of"}

    @pytest.mark.parametrize(
        "phrase",
        [
            "as of 2026-06-01",
            "verified on 2026-06-01",
            "checked on 2026-06-01",
            "rechecked 2026-06-01",
        ],
    )
    def test_every_as_of_phrase_is_recognised(self, tmp_path: Path, phrase: str) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-06-01", phrase)})
        commit_head(root, {SKILL: _skill("2026-11-01", phrase)})
        assert rules(drift(root)) == {"stale-as-of"}

    def test_a_month_year_as_of_is_compared_by_month(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-06-01", "as of June 2026")})
        commit_head(root, {SKILL: _skill("2026-11-01", "as of June 2026")})
        assert rules(drift(root)) == {"stale-as-of"}


class TestNegatives:
    def test_an_as_of_in_the_same_month_as_the_added_date_is_clean(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-11-01", "as of November 2026")})
        commit_head(root, {SKILL: _skill("2026-11-15", "as of November 2026")})
        assert drift(root) == []

    def test_an_as_of_equal_to_the_added_date_is_clean(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {SKILL: _skill("2026-06-01", "rechecked on 2026-11-01")})
        commit_head(root, {SKILL: _skill("2026-11-01", "rechecked on 2026-11-01")})
        assert drift(root) == []

    def test_an_added_date_more_than_three_lines_away_is_clean(self, tmp_path: Path) -> None:
        pad = "\n".join(f"- filler {n}" for n in range(4))
        text = f"- Limit (2026-11-01)\n{pad}\n- rechecked on 2026-06-01\n"
        root = make_repo(tmp_path, {SKILL: text.replace("2026-11-01", "2026-06-01")})
        commit_head(root, {SKILL: text})
        assert drift(root) == []

    def test_an_added_date_exactly_three_lines_away_counts(self, tmp_path: Path) -> None:
        pad = "\n".join(f"- filler {n}" for n in range(2))
        text = f"- Limit (2026-11-01)\n{pad}\n- rechecked on 2026-06-01\n"
        root = make_repo(tmp_path, {SKILL: text.replace("2026-11-01", "2026-06-01")})
        commit_head(root, {SKILL: text})
        assert rules(drift(root)) == {"stale-as-of"}

    def test_a_date_the_diff_did_not_add_is_clean(self, tmp_path: Path) -> None:
        text = _skill("2026-11-01")
        root = make_repo(tmp_path, {SKILL: text})
        commit_head(root, {SKILL: text + "\nUnrelated paragraph.\n"})
        assert drift(root) == []

    def test_an_as_of_in_a_fence_is_skipped(self, tmp_path: Path) -> None:
        text = "- Limit (2026-11-01)\n```\nrechecked on 2026-06-01\n```\n"
        root = make_repo(tmp_path)
        commit_head(root, {SKILL: text})
        assert drift(root) == []

    def test_the_ignore_marker_silences_it(self, tmp_path: Path) -> None:
        text = (
            "- Limit (2026-11-01)\n"
            "<!-- doc-date-drift: ignore -- the recheck is of a different page -->\n"
            "- rechecked on 2026-06-01\n"
        )
        root = make_repo(tmp_path)
        commit_head(root, {SKILL: text})
        assert drift(root) == []
