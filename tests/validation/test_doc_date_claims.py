"""Pure matching logic for the doc-date-drift gate (no git, no files)."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.validation import doc_date_claims as claims


class TestSkillNameFor:
    @pytest.mark.parametrize(
        ("path", "name"),
        [
            ("src/claude/skills/adr-review/references/a.md", "adr-review"),
            ("src/claude/skills/adr-review/SKILL.md", "adr-review"),
            ("templates/skills/adr-review.SKILL.md.tmpl", "adr-review"),
            ("templates/skills/adr-review/notes.md", "adr-review"),
            (".claude/skills/adr-review/references/a.md", "adr-review"),
            ("docs/skills/adr-review.md", "adr-review"),
        ],
    )
    def test_resolves_a_skill(self, path: str, name: str) -> None:
        assert claims.skill_name_for(path) == name

    @pytest.mark.parametrize(
        "path",
        [
            "docs/skills/README.md",
            "docs/guide.md",
            "templates/skills/partials/no-generated-headers.mustache",
            "src/claude/rules/x.md",
            "docs/skills/nested/x.md",
        ],
    )
    def test_returns_none_outside_a_skill(self, path: str) -> None:
        assert claims.skill_name_for(path) is None


class TestNormalizeUrl:
    def test_variants_of_one_url_share_a_key(self) -> None:
        forms = [
            "https://www.Example.com/a/b/",
            "http://example.com/a/b",
            "HTTPS://EXAMPLE.COM/a/b/#section",
        ]
        assert len({claims.normalize_url(form) for form in forms}) == 1

    def test_different_paths_differ(self) -> None:
        assert claims.normalize_url("https://e.com/a") != claims.normalize_url("https://e.com/b")


class TestSubjectClaims:
    def test_url_with_updated_year_uses_the_updated_year(self) -> None:
        (claim,) = claims.claims_for_line("See https://e.com/p/2023/x (2023, updated 2025).")
        assert (claim.rule, claim.value) == ("subject-drift", "2025")

    def test_without_updated_the_maximum_year_is_used(self) -> None:
        (claim,) = claims.claims_for_line("See https://e.com/p (2019 and 2024 editions).")
        assert claim.value == "2024"

    def test_iso_dates_count_at_year_granularity(self) -> None:
        (claim,) = claims.claims_for_line("See https://e.com/p (accessed 2026-03-04).")
        assert claim.value == "2026"

    def test_a_year_inside_the_url_is_not_a_claim(self) -> None:
        assert claims.claims_for_line("See https://e.com/2023/04/05/post.html for details.") == []

    def test_a_year_inside_the_quoted_title_is_not_a_claim(self) -> None:
        assert claims.claims_for_line('Read "Release Notes 2023 Edition" today.') == []

    def test_url_and_title_on_one_line_give_two_keys_one_value(self) -> None:
        found = claims.claims_for_line('"Review Guide Book" https://e.com/p (2025)')
        assert len({c.key for c in found}) == 2
        assert {c.value for c in found} == {"2025"}

    def test_trailing_punctuation_is_not_part_of_the_url(self) -> None:
        (a,) = claims.claims_for_line("(https://e.com/p) 2025")
        (b,) = claims.claims_for_line("https://e.com/p. 2025")
        assert a.key == b.key

    def test_no_year_means_no_claim(self) -> None:
        assert claims.claims_for_line("See https://e.com/p for details.") == []


class TestVersionClaims:
    @pytest.mark.parametrize(
        ("line", "key", "version"),
        [
            ("Tested with Copilot CLI 1.0.109", "copilot cli", "1.0.109"),
            ("Use ruff v0.9.1 here", "ruff", "0.9.1"),
            ("Run `npx @github/copilot@1.0.109`", "@github/copilot", "1.0.109"),
            ("Pinned `ruff` 0.9.1 in CI", "ruff", "0.9.1"),
            ("Needs Python 3.14", "python", "3.14"),
        ],
    )
    def test_extracts_name_and_version(self, line: str, key: str, version: str) -> None:
        found = [c for c in claims.claims_for_line(line) if c.rule == "version-drift"]
        assert [(c.key, c.value) for c in found] == [(key, version)]

    @pytest.mark.parametrize(
        "line",
        [
            "Step 1.2 covers setup",
            "Section 4.2 covers setup",
            "Supported since Copilot CLI 1.0.50",
            "Added in 1.0.50",
            "Copilot CLI >= 1.0.100",
            "Copilot CLI 1.0.100 was deprecated",
            "Copilot CLI 1.0.100 changelog",
            "Server at 10.0.0.1 answers",
            "Costs 0.5 dollars",
        ],
    )
    def test_no_version_claim(self, line: str) -> None:
        assert [c for c in claims.claims_for_line(line) if c.rule == "version-drift"] == []

    def test_a_leading_blockquote_marker_is_not_a_history_word(self) -> None:
        found = claims.claims_for_line("> Tested with Copilot CLI 1.0.109")
        assert [c.value for c in found if c.rule == "version-drift"] == ["1.0.109"]

    def test_a_version_inside_an_html_comment_is_not_a_claim(self) -> None:
        line = "See notes. <!-- Tested with Copilot CLI 1.0.100 -->"
        assert [c for c in claims.claims_for_line(line) if c.rule == "version-drift"] == []


class TestHeaderDates:
    def test_reads_last_and_next_with_line_numbers(self) -> None:
        lines = ["**Last Updated**: 2026-01-08", "x", "**Next Review**: 2026-01-22"]
        found = claims.header_dates(lines)
        assert [(h.kind, h.line, h.value) for h in found] == [
            ("last", 1, date(2026, 1, 8)),
            ("next", 3, date(2026, 1, 22)),
        ]

    def test_first_line_offsets_the_numbers(self) -> None:
        (found,) = claims.header_dates(["last_updated: 2026-01-08"], first_line=5)
        assert found.line == 5

    def test_an_invalid_calendar_date_is_skipped(self) -> None:
        assert claims.header_dates(["Last Updated: 2026-13-45"]) == []

    def test_a_label_without_a_date_is_skipped(self) -> None:
        assert claims.header_dates(["Last Updated: soon"]) == []


class TestSuggestNextReview:
    def test_uses_the_prior_interval_when_positive(self) -> None:
        assert claims.suggest_next_review(date(2026, 10, 24), 14) == date(2026, 11, 7)

    @pytest.mark.parametrize("prior", [None, 0, -5])
    def test_falls_back_to_ninety_days(self, prior: int | None) -> None:
        assert claims.suggest_next_review(date(2026, 10, 24), prior) == date(2027, 1, 22)


class TestReasonedIgnore:
    def test_marker_with_reason_on_the_line(self) -> None:
        lines = ["x <!-- doc-date-drift: ignore -- because -->"]
        assert claims.has_reasoned_ignore(lines, 1, lines[0])

    def test_marker_with_reason_on_the_line_above(self) -> None:
        lines = ["<!-- doc-date-drift: ignore -- because -->", "x"]
        assert claims.has_reasoned_ignore(lines, 2, lines[1])

    def test_marker_without_reason_does_not_count(self) -> None:
        lines = ["x <!-- doc-date-drift: ignore -->"]
        assert not claims.has_reasoned_ignore(lines, 1, lines[0])

    def test_first_line_has_no_line_above(self) -> None:
        assert not claims.has_reasoned_ignore(["x"], 1, "x")
