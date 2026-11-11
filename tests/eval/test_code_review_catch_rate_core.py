"""Tests for scripts/eval/_code_review_catch_rate_core.py (issue #7149).

The git seam is a plain callable over an argv tuple, so no repository is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _code_review_catch_rate_core as core  # noqa: E402

INTRO, FIX = "a" * 40, "b" * 40
INTRO_PATCH = (
    "diff --git a/scripts/tool.py b/scripts/tool.py\n"
    "+++ b/scripts/tool.py\n"
    "+    handle = open(path)  # never closed on the error path\n"
)
FIX_PATCH = (
    "diff --git a/scripts/tool.py b/scripts/tool.py\n"
    "+++ b/scripts/tool.py\n"
    "+    with open(path) as handle:  # the corrected resource handling in the fix\n"
)


def _raw_entry(**over):
    base = {
        "id": "CR01",
        "introducer": INTRO,
        "fix": FIX,
        "introducer_ref": "PR #100",
        "link_evidence": "Fixes the leak PR #100 introduced.",
        "defect": "The file handle is never closed on the error path.",
        "defect_files": ["scripts/tool.py"],
        "defect_class": "resource-handling",
        "confidence": "high",
    }
    return {**base, **over}


def _payload(entries=None, **over):
    base = {
        "schema_version": 1,
        "selection": {"rule": "explicit introducer link"},
        "entries": [_raw_entry()] if entries is None else entries,
    }
    return {**base, **over}


class FakeGit:
    """Answers the git calls the core module makes and records every argv."""

    def __init__(self, files="scripts/tool.py\ndocs/note.md\n"):
        self.calls: list[tuple[str, ...]] = []
        self.files = files

    def __call__(self, args):
        self.calls.append(args)
        if args[0] != "show":
            return None
        commit = args[1]
        if "--name-only" in args:
            return self.files
        if "--no-patch" in args:
            return "intro subject\n" if commit == INTRO else "fix: repair the leak\n"
        return INTRO_PATCH if commit == INTRO else FIX_PATCH


class TestCorpusParsing:
    def test_valid_payload_parses(self):
        corpus = core.parse_corpus(_payload())

        assert [e.id for e in corpus.entries] == ["CR01"]
        assert corpus.entries[0].defect_files == ("scripts/tool.py",)

    @pytest.mark.parametrize(
        ("entry", "fragment"),
        [
            ({"id": "X1"}, "must look like CR01"),
            ({"introducer": "short"}, "40-hex"),
            ({"fix": INTRO}, "same commit"),
            ({"defect_class": "style"}, "class list"),
            ({"defect_files": []}, "missing defect_files"),
            ({"defect": ""}, "missing defect"),
            ({"link_evidence": ""}, "missing link_evidence"),
        ],
    )
    def test_bad_entry_is_refused(self, entry, fragment):
        with pytest.raises(core.CorpusError, match=fragment):
            core.parse_corpus(_payload([_raw_entry(**entry)]))

    def test_missing_selection_rule_is_refused(self):
        with pytest.raises(core.CorpusError, match="selection.rule"):
            core.parse_corpus(_payload(selection={}))

    def test_duplicate_ids_and_empty_corpus_are_refused(self):
        with pytest.raises(core.CorpusError, match="duplicate"):
            core.parse_corpus(_payload([_raw_entry(), _raw_entry()]))
        with pytest.raises(core.CorpusError, match="no entries"):
            core.parse_corpus(_payload([]))

    def test_unknown_schema_version_is_refused(self):
        with pytest.raises(core.CorpusError, match="schema_version"):
            core.parse_corpus(_payload(schema_version=2))

    @pytest.mark.parametrize("entries", [None, {"a": 1}, "text", [1], [[]], [None]])
    def test_entries_that_are_not_a_list_of_objects_are_refused(self, entries):
        with pytest.raises(core.CorpusError, match="list of objects"):
            core.parse_corpus(
                _payload(entries=entries)
                if entries is not None
                else {**_payload(), "entries": None}
            )

    def test_unreadable_corpus_file_is_refused(self, tmp_path):
        with pytest.raises(core.CorpusError, match="cannot read"):
            core.load_corpus(tmp_path / "absent.json")


class TestReviewInput:
    def test_diff_excludes_documentation_files(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())

        review = core.build_review_input(entry, "SYSTEM", git)

        assert review.files_shown == ("scripts/tool.py",)
        show_patch = [c for c in git.calls if "-p" in c]
        assert show_patch and "docs/note.md" not in show_patch[0]

    def test_prompt_carries_diff_subject_and_class_list(self):
        review = core.build_review_input(core.parse_entry(_raw_entry()), "SYSTEM", FakeGit())

        assert "handle = open(path)" in review.user
        assert "intro subject" in review.user
        assert "resource-handling" in review.user and "FINDING:" in review.user
        assert review.system == "SYSTEM"

    def test_reading_the_reviewer_input_never_touches_the_fixing_commit(self):
        git = FakeGit()

        core.build_review_input(core.parse_entry(_raw_entry()), "SYSTEM", git)

        assert git.calls
        assert all(FIX not in call for call in git.calls)

    def test_defect_file_outside_the_reviewed_diff_is_refused(self):
        entry = core.parse_entry(_raw_entry(defect_files=["scripts/other.py"]))

        with pytest.raises(core.CorpusError, match="not in the reviewed diff"):
            core.build_review_input(entry, "SYSTEM", FakeGit())

    def test_unreadable_introducer_and_docs_only_commit_are_refused(self):
        entry = core.parse_entry(_raw_entry())

        with pytest.raises(core.CorpusError, match="not readable"):
            core.build_review_input(entry, "SYSTEM", lambda args: None)
        with pytest.raises(core.CorpusError, match="no reviewable file"):
            core.build_review_input(entry, "SYSTEM", FakeGit(files="docs/note.md\n"))

    def test_oversized_diff_is_refused(self, monkeypatch):
        monkeypatch.setattr(core, "MAX_DIFF_CHARS", 10)

        with pytest.raises(core.CorpusError, match="cap"):
            core.build_review_input(core.parse_entry(_raw_entry()), "SYSTEM", FakeGit())


class TestLeakCheck:
    def test_clean_prompt_has_no_leak(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())
        review = core.build_review_input(entry, "SYSTEM", git)

        assert core.check_no_leak(entry, review, git) == []

    def test_unreadable_fixing_commit_is_refused_not_passed_vacuously(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())
        review = core.build_review_input(entry, "SYSTEM", git)

        def fix_missing(args):
            return None if FIX in args else git(args)

        with pytest.raises(core.CorpusError, match="not readable"):
            core.check_no_leak(entry, review, fix_missing)

    def test_fix_content_in_the_prompt_is_detected(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())
        review = core.build_review_input(entry, "SYSTEM", git)
        leaky = core.ReviewInput(
            entry=review.entry,
            system=review.system,
            user=review.user + "\nfix: repair the leak\n" + FIX[:12],
            diff_chars=review.diff_chars,
            files_shown=review.files_shown,
        )

        reasons = core.check_no_leak(entry, leaky, git)

        assert "fix subject" in reasons and any("fix sha" in r for r in reasons)

    def test_fix_added_line_in_the_prompt_is_detected(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())
        review = core.build_review_input(entry, "SYSTEM", git)
        added = "with open(path) as handle:  # the corrected resource handling in the fix"
        leaky = core.ReviewInput(entry.id, review.system, review.user + added, 0, ())

        assert any("fix line" in r for r in core.check_no_leak(entry, leaky, git))

    def test_defect_description_in_the_prompt_is_detected(self):
        git = FakeGit()
        entry = core.parse_entry(_raw_entry())
        leaky = core.ReviewInput(entry.id, "SYSTEM", entry.defect, 0, ())

        assert "corpus defect description" in core.check_no_leak(entry, leaky, git)
