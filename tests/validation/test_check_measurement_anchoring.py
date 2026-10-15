"""Claim detection and exit codes for the measurement-anchoring gate (issue #5771).

Every case drives ``main(argv)`` against a real throwaway repository and
asserts the exit code, per ``.claude/rules/testing.md`` MUST 8. The pure
classifier is also pinned directly, because its regexes are the part that
drifts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import measurement_claims as claims
from tests.validation.measurement_anchoring_helpers import (
    ANCHORED,
    DATED,
    THRESHOLD,
    UNANCHORED,
    _add_doc,
    _repo,
    _run,
    checker,
    cite,
)


class TestRecommendationThreeFalsifier:
    """The three cases the issue's falsifier names, as written."""

    def test_unanchored_tree_state_claim_exits_1_and_names_file_and_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/architecture.md", f"intro\n{UNANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert cite("docs/architecture.md", 2) in out
        assert "47 tracked files" in out

    def test_same_line_with_a_commit_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/architecture.md", f"intro\n{ANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 0
        assert "examined 2 line(s) across 1 file(s)" in out

    def test_policy_threshold_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/architecture.md", f"intro\n{THRESHOLD}\n")
        code, _out = _run(root, capsys)
        assert code == 0


class TestAnchors:
    @pytest.mark.parametrize(
        "line",
        [
            ANCHORED,
            DATED,
            "This tree holds 47 tracked files (as of v1.2.3).",
            "This tree holds 47 tracked files (as of 55ec6212c0f).",
        ],
    )
    def test_anchor_kinds_clear_the_line(self, line: str) -> None:
        assert claims.unanchored_claims(line) == []

    @pytest.mark.parametrize(
        "line",
        [
            "This tree holds 47 tracked files (see 1234567).",
            "This tree holds 47 tracked files in 2026.",
            "This tree holds 47 tracked files (ABCDEF1).",
        ],
    )
    def test_non_anchors_do_not_clear_the_line(self, line: str) -> None:
        assert claims.unanchored_claims(line) == ["47 tracked files"]


class TestClaimShapes:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("9,765 tracked files today", "9,765 tracked files"),
            ("There are 23 agents under `.claude/agents/`.", "23 agents under `.claude/agents/`"),
            ("Skills | Yes (109 in `src/claude/skills/`)", "109 in `src/claude/skills/`"),
            ("We keep 56 files in `.github/workflows/`.", "56 files in `.github/workflows/`"),
            ("There are 29 rules in the tree.", "29 rules in the tree"),
            ("Holds 12 open issues on main now.", "12 open issues on main"),
            ("It has 3 skills in this repository.", "3 skills in this repository"),
        ],
    )
    def test_tree_state_shapes_are_claims(self, line: str, expected: str) -> None:
        assert claims.tree_state_claims(line) == [expected]

    @pytest.mark.parametrize(
        "line",
        [
            "Max 15 skills in `.claude/skills/`.",
            "Keep it at most 20 files in `docs/x/`.",
            "Methods stay under 60 lines.",
            "We ship 3 skills.",
            "Issue #5771 files in `scripts/` changed.",
            "Step 0.5 lives in `references/gate.md`.",
            "Exit 1 files in `scripts/` fail.",
            "Section 4 files in `docs/x/` explain it.",
            "The 5 in `scripts/example.py` is a line number.",
            "ADR-064 files in `docs/x/` cite it.",
            "Open 1 heading in `docs/spec.md`.",
        ],
    )
    def test_thresholds_labels_and_unqualified_counts_are_not_claims(self, line: str) -> None:
        assert claims.tree_state_claims(line) == []

    def test_words_between_the_noun_and_the_repo_qualifier_stay_one_claim(self) -> None:
        line = "It holds 12 open issues filed against us in this repository."
        assert claims.tree_state_claims(line) == [
            "12 open issues filed against us in this repository"
        ]

    def test_a_sentence_break_before_the_qualifier_is_not_a_claim(self) -> None:
        assert claims.tree_state_claims("It holds 12 open issues. Rest lives on main.") == []

    def test_a_gap_over_sixty_characters_is_not_a_claim(self) -> None:
        gap = "x" * 61
        assert claims.tree_state_claims(f"It holds 12 open issues {gap} on main.") == []

    def test_repeated_phrase_is_reported_once(self) -> None:
        line = "23 agents under `a/` and again 23 agents under `a/`."
        assert claims.tree_state_claims(line) == ["23 agents under `a/`"]


class TestMarkdownStructure:
    def test_heading_is_recognised(self) -> None:
        assert claims.is_heading("## 47 tracked files")
        assert not claims.is_heading("#47 tracked files")

    def test_fenced_lines_include_the_fences(self) -> None:
        lines = ["a", "```text", UNANCHORED, "```", "b", "~~~", "x", "~~~~", "y"]
        assert claims.fenced_line_numbers(lines) == {2, 3, 4, 6, 7, 8}

    def test_shorter_closing_fence_does_not_close(self) -> None:
        lines = ["````", "```", "still inside", "````", "outside"]
        assert claims.fenced_line_numbers(lines) == {1, 2, 3, 4}

    def test_other_marker_does_not_close(self) -> None:
        lines = ["```", "~~~", "inside", "```", "outside"]
        assert claims.fenced_line_numbers(lines) == {1, 2, 3, 4}

    def test_fenced_claim_exits_0(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", f"```text\n{UNANCHORED}\n```\n")
        code, _out = _run(root, capsys)
        assert code == 0

    def test_heading_claim_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", "## 47 tracked files\n")
        code, _out = _run(root, capsys)
        assert code == 0


class TestExitCodes:
    def test_not_a_git_repository_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = checker.main(["--repo-root", str(tmp_path), "--base", "main"])
        assert code == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_unknown_base_ref_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        code = checker.main(["--repo-root", str(root), "--base", "no-such-ref"])
        assert code == 2
        assert "git failed" in capsys.readouterr().err

    def test_multiple_claims_on_one_line_are_each_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", "5 skills under `a/` and 6 agents under `b/`.\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert "2 unanchored count(s)" in out
