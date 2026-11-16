"""Tests for scripts/eval/_third_party_gap_core.py.

The git seam is a plain callable over an argv tuple, so no repository is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _third_party_gap_core as core  # noqa: E402

BASE, HEAD, FIX = "a" * 40, "b" * 40, "c" * 40
PATCH = (
    "diff --git a/scripts/tool.py b/scripts/tool.py\n"
    "--- a/scripts/tool.py\n"
    "+++ b/scripts/tool.py\n"
    "@@ -10,3 +10,4 @@ def f():\n"
    " keep\n"
    "-old\n"
    "+new one\n"
    "+new two\n"
    " tail\n"
    "\\ No newline at end of file\n"
)
FIX_PATCH = (
    "+++ b/scripts/tool.py\n+    return handle.close_and_report_every_error_that_occurred()\n"
)


def defect(**over: Any) -> dict[str, Any]:
    raw = {
        "thread": "T0001",
        "bot": "cursor",
        "path": "scripts/tool.py",
        "line": 11,
        "fix": FIX,
        "context": "diff-local",
        "summary": "new one drops the error",
    }
    return {**raw, **over}


def revision(**over: Any) -> dict[str, Any]:
    raw = {
        "id": "TG001",
        "pr": 7,
        "base": BASE,
        "head": HEAD,
        "split": "heldout",
        "defects": [defect()],
    }
    return {**raw, **over}


def corpus(*revs: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "selection": {"rule": "r"},
        "revisions": list(revs) or [revision()],
    }


def fake_git(names: str = "scripts/tool.py\n", patch: str = PATCH) -> core.GitRun:
    def git(args: tuple[str, ...]) -> str | None:
        if args[:2] == ("diff", "--name-only"):
            return names
        if args[0] == "diff":
            return patch
        if args[:2] == ("show", FIX) and "--format=%s" in args:
            return "fix(tool): close the handle\n"
        if args[:2] == ("show", FIX):
            return FIX_PATCH
        raise AssertionError(f"unexpected git call {args}")

    return git


class TestParseCorpus:
    def test_valid_corpus_parses(self) -> None:
        _, revs = core.parse_corpus(corpus())

        assert revs[0].defects[0].line == 11

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"id": "X1"}, "TG001"),
            ({"base": "zz"}, "40-hex"),
            ({"split": "train"}, "split"),
            ({"defects": []}, "non-empty"),
            ({"pr": "7"}, "integer"),
            ({"defects": [defect(context="vibes")]}, "context"),
            ({"defects": [defect(line=0)]}, "positive"),
            ({"defects": [defect(path="")]}, "path"),
        ],
    )
    def test_malformed_revision_is_refused(self, over: dict[str, Any], message: str) -> None:
        with pytest.raises(core.CorpusError, match=message):
            core.parse_corpus(corpus(revision(**over)))

    def test_duplicate_id_is_refused(self) -> None:
        with pytest.raises(core.CorpusError, match="duplicate"):
            core.parse_corpus(corpus(revision(), revision()))

    def test_missing_selection_rule_is_refused(self) -> None:
        with pytest.raises(core.CorpusError, match="selection.rule"):
            core.parse_corpus({"schema_version": 1, "selection": {}, "revisions": [revision()]})


class TestNumberNewLines:
    def test_added_and_context_lines_carry_new_file_numbers(self) -> None:
        lines = core.number_new_lines(PATCH).splitlines()

        assert "10\t keep" in lines
        assert "\t-old" in lines
        assert "11\t+new one" in lines
        assert "13\t tail" in lines
        assert lines[-1] == "\\ No newline at end of file"


class TestParseAndScore:
    def test_finding_line_number_is_read(self) -> None:
        (finding,) = core.parse_findings("FINDING: `scripts/tool.py:12` | edge-case | drops it")

        assert (finding.path, finding.line, finding.klass) == ("scripts/tool.py", 12, "edge-case")

    def test_finding_without_line_has_none(self) -> None:
        (finding,) = core.parse_findings("- **FINDING**: scripts/tool.py | logic-error | bad")

        assert finding.line is None

    @pytest.mark.parametrize(
        ("line", "caught"), [(11 + core.LINE_WINDOW, True), (12 + core.LINE_WINDOW, False)]
    )
    def test_line_window_boundary(self, line: int, caught: bool) -> None:
        findings = core.parse_findings(f"FINDING: scripts/tool.py:{line} | edge-case | x")

        got = core.score_defect(findings, core.parse_defect(defect(), "t"))

        assert got == {"caught": caught, "same_file": True}

    def test_only_first_top_n_findings_count(self) -> None:
        filler = "\n".join(f"FINDING: other.py:{i} | edge-case | x" for i in range(core.TOP_N))
        raw = filler + "\nFINDING: scripts/tool.py:11 | edge-case | late"

        got = core.score_defect(core.parse_findings(raw), core.parse_defect(defect(), "t"))

        assert got == {"caught": False, "same_file": False}

    def test_score_revision_reports_no_findings(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())

        got = core.score_revision("NO FINDINGS\nVERDICT: PASS", rev)

        assert got["no_findings"] is True
        assert got["defects"]["T0001"] == {"caught": False, "same_file": False}


class TestBuildReviewInput:
    def test_prompt_numbers_lines_and_names_the_title(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())

        review = core.build_review_input(rev, "feat: tool", "SYSTEM", fake_git())

        assert "Change under review: feat: tool" in review.user
        assert "11\t+new one" in review.user
        assert review.files_shown == ("scripts/tool.py",)

    def test_defect_path_outside_the_diff_is_refused(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())

        with pytest.raises(core.CorpusError, match="not in the reviewed diff"):
            core.build_review_input(rev, "t", "S", fake_git(names="other.py\n"))

    def test_oversized_diff_is_refused(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())
        big = PATCH + "+x\n" * core.MAX_DIFF_CHARS

        with pytest.raises(core.CorpusError, match="cap"):
            core.build_review_input(rev, "t", "S", fake_git(patch=big))

    def test_lockfiles_are_not_shown(self) -> None:
        assert core.reviewable_files(["a.py", "uv.lock", "x.jsonl"]) == ["a.py"]


class TestCheckNoLeak:
    def test_unreadable_revision_diff_raises(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())
        review = core.build_review_input(rev, "t", "S", fake_git())
        inner = fake_git()

        def git(args: tuple[str, ...]) -> str | None:
            return None if args == ("diff", rev.base, rev.head) else inner(args)

        with pytest.raises(core.CorpusError, match="not readable"):
            core.check_no_leak(rev, review, git)

    def test_clean_prompt_has_no_reasons(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())
        review = core.build_review_input(rev, "t", "S", fake_git())

        assert core.check_no_leak(rev, review, fake_git()) == []

    def test_fix_line_in_system_prompt_is_reported(self) -> None:
        _, (rev,) = core.parse_corpus(corpus())
        system = "return handle.close_and_report_every_error_that_occurred()"
        review = core.build_review_input(rev, "t", system, fake_git())

        assert core.check_no_leak(rev, review, fake_git())
