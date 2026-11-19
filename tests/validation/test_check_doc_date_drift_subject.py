"""Rules ``subject-drift`` and ``version-drift`` (PR #7428 shape and version bumps)."""

from __future__ import annotations

from pathlib import Path

from tests.validation.doc_date_drift_helpers import commit_head, drift, make_repo, rules, where

URL = "https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html"
DOCS = "docs/skills/adr-review.md"
REF = "src/claude/skills/adr-review/references/zimmermann-review-guidance.md"


def _cite(updated: str) -> str:
    return f'Zimmermann, "ADR Review", {URL} (2023, updated {updated}).\n'


def _reference(updated: str) -> str:
    filler = "\n".join(f"filler line {n}" for n in range(4, 94))
    return f"# Guidance\n\n{_cite(updated)}{filler}\n{_cite(updated)}"


def _pr7428_repo(tmp_path: Path) -> Path:
    base = {DOCS: _cite("2025"), REF: _reference("2025")}
    return make_repo(tmp_path, base)


class TestPr7428Repro:
    def test_updating_only_the_docs_page_flags_both_reference_citations(
        self, tmp_path: Path
    ) -> None:
        root = _pr7428_repo(tmp_path)
        commit_head(root, {DOCS: _cite("2026")})
        findings = drift(root)
        assert {where(f) for f in findings} == {(REF, 3), (REF, 94)}
        assert rules(findings) == {"subject-drift"}
        assert {f.suggested for f in findings} == {"2026"}
        assert {(f.other_path, f.other_line) for f in findings} == {(DOCS, 1)}

    def test_updating_both_files_together_is_clean(self, tmp_path: Path) -> None:
        root = _pr7428_repo(tmp_path)
        commit_head(root, {DOCS: _cite("2026"), REF: _reference("2026")})
        assert drift(root) == []

    def test_consistent_years_are_clean(self, tmp_path: Path) -> None:
        root = _pr7428_repo(tmp_path)
        commit_head(root, {DOCS: _cite("2025") + "Another paragraph.\n"})
        assert drift(root) == []

    def test_the_year_inside_the_url_path_is_not_a_claim(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {REF: f"See {URL} (2023).\n"})
        commit_head(root, {DOCS: f"See {URL} (2023).\n"})
        assert drift(root) == []

    def test_one_stale_line_disagreeing_with_two_added_lines_is_one_finding(
        self, tmp_path: Path
    ) -> None:
        root = make_repo(tmp_path, {DOCS: _cite("2025"), REF: _cite("2025")})
        commit_head(root, {DOCS: _cite("2026") + _cite("2026")})
        (finding,) = drift(root)
        assert where(finding) == (REF, 1)
        assert (finding.other_path, finding.other_line) == (DOCS, 1)

    def test_the_same_url_in_another_skills_tree_is_not_searched(self, tmp_path: Path) -> None:
        other = "src/claude/skills/other-skill/references/notes.md"
        root = make_repo(tmp_path, {DOCS: _cite("2025"), other: _cite("2025")})
        commit_head(root, {DOCS: _cite("2026")})
        assert drift(root) == []

    def test_url_normalisation_ignores_scheme_www_slash_fragment_and_case(
        self, tmp_path: Path
    ) -> None:
        ref = (
            "Source: http://OZIMMER.ch/practices/2023/04/05/ADRReview.html/#top "
            "(2023, updated 2025)\n"
        )
        root = make_repo(tmp_path, {REF: ref})
        commit_head(root, {DOCS: _cite("2026")})
        assert where(drift(root)[0]) == (REF, 1)

    def test_a_year_pair_in_a_fenced_block_is_skipped(self, tmp_path: Path) -> None:
        fenced = f"```\n{_cite('2025')}```\n"
        root = make_repo(tmp_path, {REF: fenced})
        commit_head(root, {DOCS: _cite("2026")})
        assert drift(root) == []

    def test_an_added_year_pair_inside_a_fence_makes_no_claim(self, tmp_path: Path) -> None:
        root = _pr7428_repo(tmp_path)
        commit_head(root, {DOCS: f"```\n{_cite('2026')}```\n"})
        assert drift(root) == []

    def test_the_ignore_marker_on_the_stale_line_silences_it(self, tmp_path: Path) -> None:
        ref = "<!-- doc-date-drift: ignore -- quotes the 2025 edition on purpose -->\n" + _cite(
            "2025"
        )
        root = make_repo(tmp_path, {REF: ref})
        commit_head(root, {DOCS: _cite("2026")})
        assert drift(root) == []


class TestTitleSubjects:
    def test_a_quoted_title_with_a_different_year_is_flagged(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {REF: 'See "Architecture Decision Review Guide" (2023).\n'})
        commit_head(root, {DOCS: 'The "architecture decision review guide!" (2025) is current.\n'})
        (finding,) = drift(root)
        assert where(finding) == (REF, 1)
        assert finding.suggested == "2025"

    def test_a_short_quoted_word_is_not_a_subject(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {REF: 'The "ADR" (2023).\n'})
        commit_head(root, {DOCS: 'The "ADR" (2025).\n'})
        assert drift(root) == []

    def test_updated_year_wins_over_the_publication_year(self, tmp_path: Path) -> None:
        root = make_repo(
            tmp_path, {REF: 'See "Architecture Decision Review Guide" (2023, updated 2025).\n'}
        )
        commit_head(
            root, {DOCS: 'See "Architecture Decision Review Guide" (2019, updated 2025).\n'}
        )
        assert drift(root) == []


class TestVersionDrift:
    SKILL = "templates/skills/copilot.SKILL.md.tmpl"
    REF = "src/claude/skills/copilot/references/x.md"

    def test_the_same_tool_with_a_different_version_is_flagged(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Tested with Copilot CLI 1.0.100\n"})
        commit_head(root, {self.SKILL: "# Copilot\n\nTested with Copilot CLI 1.0.109\n"})
        (finding,) = drift(root)
        assert finding.rule == "version-drift"
        assert where(finding) == (self.REF, 1)
        assert finding.suggested == "1.0.109"
        assert (finding.other_path, finding.other_line) == (self.SKILL, 3)

    def test_the_same_version_is_clean(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Tested with Copilot CLI 1.0.109\n"})
        commit_head(root, {self.SKILL: "Tested with Copilot CLI 1.0.109\n"})
        assert drift(root) == []

    def test_history_lines_are_not_flagged(self, tmp_path: Path) -> None:
        old = "Copilot CLI 1.0.50 hooks were added in this release.\n"
        root = make_repo(tmp_path, {self.REF: old})
        commit_head(root, {self.SKILL: "Tested with Copilot CLI 1.0.109\n"})
        assert drift(root) == []

    def test_a_history_word_on_the_added_line_suppresses_the_claim(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Tested with Copilot CLI 1.0.100\n"})
        commit_head(root, {self.SKILL: "Copilot CLI 1.0.109 removed the flag.\n"})
        assert drift(root) == []

    def test_two_different_tools_sharing_a_trailing_word_do_not_collide(
        self, tmp_path: Path
    ) -> None:
        root = make_repo(tmp_path, {self.REF: "Tested with Copilot CLI 1.0.100\n"})
        commit_head(root, {self.SKILL: "Tested with Gemini CLI 2.0.0\n"})
        assert drift(root) == []

    def test_at_version_form(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Run `npx @github/copilot@1.0.100`.\n"})
        commit_head(root, {self.SKILL: "Run `npx @github/copilot@1.0.109`.\n"})
        (finding,) = drift(root)
        assert finding.rule == "version-drift"

    def test_backtick_name_form(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Pinned `ruff` 0.8.0 in CI.\n"})
        commit_head(root, {self.SKILL: "Pinned `ruff` 0.9.1 in CI.\n"})
        (finding,) = drift(root)
        assert finding.suggested == "0.9.1"

    def test_label_words_are_not_tool_names(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "Step 1.2 covers setup.\n"})
        commit_head(root, {self.SKILL: "Step 1.3 covers setup.\n"})
        assert drift(root) == []

    def test_a_version_in_a_fence_is_skipped(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path, {self.REF: "```\nCopilot CLI 1.0.100\n```\n"})
        commit_head(root, {self.SKILL: "Copilot CLI 1.0.109\n"})
        assert drift(root) == []

    def test_the_ignore_marker_on_the_line_silences_it(self, tmp_path: Path) -> None:
        old = "Copilot CLI 1.0.100 <!-- doc-date-drift: ignore -- frozen example -->\n"
        root = make_repo(tmp_path, {self.REF: old})
        commit_head(root, {self.SKILL: "Copilot CLI 1.0.109\n"})
        assert drift(root) == []


def test_different_updated_days_in_one_year_are_drift(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {REF: _cite("2026-03-04")})
    commit_head(root, {DOCS: _cite("2026-03-05")})
    findings = drift(root)
    assert any(f.rule == "subject-drift" and f.suggested == "2026-03-05" for f in findings)


def test_year_only_and_full_updated_date_agree(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {REF: _cite("2026")})
    commit_head(root, {DOCS: _cite("2026-03-05")})
    assert not drift(root)
