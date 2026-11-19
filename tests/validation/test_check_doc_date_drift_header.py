"""Rule ``header-pair``: Last Updated / Next Review consistency (PR #6925 shape)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.validation.doc_date_drift_helpers import (
    COMMIT_DATE,
    commit_head,
    drift,
    make_repo,
    rules,
    where,
)

DOC = "docs/COST-GOVERNANCE.md"


def _header(last: str, nxt: str, label: str = "**{}**: {}") -> str:
    return (
        "# Cost Governance\n\n"
        + label.format("Last Updated", last)
        + "\n"
        + label.format("Next Review", nxt)
        + "\n"
    )


class TestPr6925Repro:
    def test_bumping_last_updated_alone_flags_the_stale_next_review(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {DOC: _header("2026-01-08", "2026-01-22")})
        commit_head(root, {DOC: _header("2026-10-24", "2026-01-22")})
        findings = drift(root)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "header-pair"
        assert where(finding) == (DOC, 4)
        assert (finding.other_path, finding.other_line) == (DOC, 3)
        assert finding.suggested == "2026-11-07"

    def test_bumping_both_lines_together_is_clean(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {DOC: _header("2026-01-08", "2026-01-22")})
        commit_head(root, {DOC: _header("2026-10-24", "2026-11-07")})
        assert drift(root) == []

    def test_a_later_section_does_not_invalidate_an_earlier_schedule(self, tmp_path: Path) -> None:
        before = (
            "# Cost\n\n## Storage\n\n**Last Updated**: 2026-11-01\n"
            "**Next Review**: 2026-12-01\n\n## Compute\n\n"
            "**Last Updated**: 2026-11-01\n**Next Review**: 2027-01-15\n"
        )
        after = before.replace(
            "## Compute\n\n**Last Updated**: 2026-11-01",
            "## Compute\n\n**Last Updated**: 2026-12-15",
            1,
        )
        root = make_repo(tmp_path, {DOC: before})
        commit_head(root, {DOC: after})
        assert drift(root) == []


class TestForms:
    @pytest.mark.parametrize(
        "label",
        ["**{}**: {}", "{}: {}", "**{}:** {}", "- {}: {}"],
        ids=["bold", "plain", "bold-colon-inside", "bullet"],
    )
    def test_body_label_forms_are_recognised(self, tmp_path: Path, label: str) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: _header("2026-10-24", "2026-10-01", label)})
        assert rules(drift(root)) == {"header-pair"}

    @pytest.mark.parametrize("key", ["last_updated", "Last-Updated", "LAST UPDATED"])
    def test_label_spelling_is_case_and_separator_tolerant(self, tmp_path: Path, key: str) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: f"{key}: 2026-10-24\nnext_review: 2026-10-01\n"})
        assert rules(drift(root)) == {"header-pair"}

    def test_last_reviewed_pairs_with_next_review(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: "**Last Reviewed**: 2026-10-24\n**Next Review**: 2026-10-24\n"})
        assert rules(drift(root)) == {"header-pair"}

    def test_frontmatter_pair_violation(self, tmp_path: Path) -> None:
        text = "---\ntitle: x\nlast_updated: 2026-10-24\nnext_review: 2026-10-01\n---\nBody\n"
        root = make_repo(tmp_path)
        commit_head(root, {DOC: text})
        (finding,) = drift(root)
        assert where(finding) == (DOC, 4)
        assert finding.other_line == 3

    def test_consistent_frontmatter_dates_are_clean(self, tmp_path: Path) -> None:
        text = "---\nlast_updated: 2026-10-24\nnext_review: 2027-01-22\n---\nBody\n"
        root = make_repo(tmp_path)
        commit_head(root, {DOC: text})
        assert drift(root) == []

    def test_a_pair_inside_a_code_fence_is_ignored(self, tmp_path: Path) -> None:
        fenced = "```\n**Last Updated**: 2026-10-24\n**Next Review**: 2026-10-01\n```\n"
        root = make_repo(tmp_path)
        commit_head(root, {DOC: fenced})
        assert drift(root) == []


class TestNextReviewRules:
    def test_next_equal_to_last_is_flagged(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: _header("2026-10-24", "2026-10-24")})
        assert rules(drift(root)) == {"header-pair"}

    def test_next_in_the_past_but_after_last_is_flagged_against_commit_date(
        self, tmp_path: Path
    ) -> None:
        # The base interval is 24 days. Last Updated is before the commit
        # date, so the suggestion is the commit date plus that interval.
        root = make_repo(tmp_path, {DOC: _header("2026-01-08", "2026-02-01")})
        commit_head(root, {DOC: _header("2026-01-10", "2026-02-01")})
        (finding,) = drift(root)
        assert finding.suggested == "2026-11-17"
        assert date.fromisoformat(finding.suggested) >= COMMIT_DATE
        assert where(finding) == (DOC, 4)

    def test_head_date_is_injectable(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: _header("2026-10-24", "2026-11-07")})
        assert drift(root) == []
        assert rules(drift(root, head_date=date(2026, 12, 1))) == {"header-pair"}

    def test_next_review_today_is_not_in_the_past(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: _header("2026-10-01", COMMIT_DATE.isoformat())})
        assert drift(root) == []


class TestSuggestedValue:
    def test_a_new_file_falls_back_to_ninety_days(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: _header("2026-10-24", "2026-10-20")})
        (finding,) = drift(root)
        assert finding.suggested == "2027-01-22"

    def test_a_non_positive_base_interval_falls_back_to_ninety_days(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {DOC: _header("2026-01-08", "2026-01-08")})
        commit_head(root, {DOC: _header("2026-10-24", "2026-01-08")})
        (finding,) = drift(root)
        assert finding.suggested == "2027-01-22"


class TestOnlyTouchedHeaders:
    def test_an_old_stale_header_the_diff_did_not_touch_is_ignored(self, tmp_path: Path) -> None:
        stale = _header("2026-01-08", "2026-01-01")
        root = make_repo(tmp_path, {DOC: stale})
        commit_head(root, {DOC: stale + "\nA new paragraph.\n"})
        assert drift(root) == []

    def test_changing_only_the_next_review_line_fires(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {DOC: _header("2026-10-24", "2027-01-22")})
        commit_head(root, {DOC: _header("2026-10-24", "2026-10-01")})
        (finding,) = drift(root)
        assert where(finding) == (DOC, 4)

    def test_a_next_review_without_a_last_line_is_ignored(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: "**Next Review**: 2020-01-01\n"})
        assert drift(root) == []

    def test_the_ignore_marker_silences_the_finding(self, tmp_path: Path) -> None:
        text = (
            "**Last Updated**: 2026-10-24\n"
            "<!-- doc-date-drift: ignore -- archived page, review is retired -->\n"
            "**Next Review**: 2026-10-01\n"
        )
        root = make_repo(tmp_path)
        commit_head(root, {DOC: text})
        assert drift(root) == []

    def test_an_ignore_marker_without_a_reason_does_not_silence(self, tmp_path: Path) -> None:
        text = (
            "**Last Updated**: 2026-10-24\n"
            "<!-- doc-date-drift: ignore -->\n"
            "**Next Review**: 2026-10-01\n"
        )
        root = make_repo(tmp_path)
        commit_head(root, {DOC: text})
        assert rules(drift(root)) == {"header-pair"}
