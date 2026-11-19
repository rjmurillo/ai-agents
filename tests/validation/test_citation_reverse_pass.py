"""Reverse pass of the citation-freshness gate: inbound citations to changed files.

The forward gate checks citations on added lines only. These fixtures
reproduce the misses it cannot see: a branch edits, moves, or deletes a
cited file without touching the document that cites it. PR #6689 and
PR #6584 are the evidence; the second shape (a bare file name, written in
the same PR that rewrote the cited file) is the one PR #5812 introduced.

Fixture citations are composed with f-strings over ``TARGET`` so this
file's own lines never present a repo-relative citation to either pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import (
    TARGET,
    TARGET_CONTENT,
    _git,
    _repo,
    _run,
)

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)
DOC = "docs/guide.md"
ANCHORED = f"The helper `magic_token` lives at {TARGET}:3-4.\n"
INSERTED_ABOVE = "# one\n# two\n# three\n" + TARGET_CONTENT + "\n"


def _run_reverse(root: Path, base: str = "main") -> tuple[int, str]:
    """Run the reverse pass CLI the way pre-push does, as a subprocess."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo-root", str(root), "--base", base],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _repo_with_doc(tmp_path: Path, doc_text: str, doc_path: str = DOC) -> Path:
    """Create a repo whose main branch already holds the citing document."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    path = root / doc_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc_text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "doc")
    _git(root, "checkout", "-q", "-B", "feature")
    return root


def _commit_file(root: Path, relpath: str, text: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "edit")


class TestMovedContent:
    """The cited file changes under a citing line the branch never touched."""

    def test_lines_inserted_above_the_anchor_report_the_new_range(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 1, out
        assert f"{DOC}:1: {TARGET}:3-4" in out
        assert f"suggested citation {TARGET}:6-7" in out

    def test_forward_pass_alone_misses_the_unchanged_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run(root, capsys)

        assert code == 0, out

    def test_anchorless_citation_to_moved_lines_is_reported(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, f"See {TARGET}:3-4 for the helper.\n")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 1, out
        assert f"suggested citation {TARGET}:6-7" in out

    def test_anchorless_citation_to_lines_edited_in_place_passes(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, f"See {TARGET}:3-4 for the helper.\n")
        _commit_file(root, TARGET, TARGET_CONTENT.replace("magic_token", "other_name") + "\n")

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 1 inbound citation" in out

    def test_change_below_the_range_keeps_the_citation_fresh(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _commit_file(root, TARGET, TARGET_CONTENT + "\nEXTRA = 3\n")

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 1 inbound citation" in out

    def test_anchorless_cite_of_a_repeated_line_is_not_called_moved(self, tmp_path: Path) -> None:
        # Line 2 is long enough to count but occurs twice, so a shifted
        # copy proves nothing about where the cited line went.
        content = "# head\nresult = compute(\n    1,\n)\nresult = compute(\n    2,\n)\n"
        root = _repo(tmp_path)
        _git(root, "checkout", "-q", "main")
        _commit_file(root, TARGET, content)
        _commit_file(root, DOC, f"See {TARGET}:2 for the opener.\n")
        _git(root, "checkout", "-q", "-B", "feature")
        _commit_file(root, TARGET, "# new\n" + content)

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 1 inbound citation" in out


class TestMovedOrDeletedFile:
    def test_renamed_target_names_the_new_path(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _git(root, "mv", TARGET, "lib/helpers.py")
        _git(root, "commit", "-q", "-m", "rename")

        code, out = _run_reverse(root)

        assert code == 1, out
        assert "not tracked at HEAD" in out
        assert "renamed to lib/helpers.py" in out
        assert "suggested citation lib/helpers.py:3-4" in out

    def test_deleted_target_is_reported(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _git(root, "rm", "-q", TARGET)
        _git(root, "commit", "-q", "-m", "delete")

        code, out = _run_reverse(root)

        assert code == 1, out
        assert "not tracked at HEAD" in out


class TestBareBasename:
    """PR #6584's shape: a slashless name the forward pass never resolves."""

    def test_bare_name_added_with_the_move_is_resolved(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        bare = TARGET.rsplit("/", 1)[1]
        (root / DOC).parent.mkdir(parents=True)
        (root / DOC).write_text(f"The helper `magic_token` is at {bare}:3.\n", encoding="utf-8")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)
        forward_code, forward_out = _run(root, capsys)

        assert code == 1, out
        assert "first appears at line 6" in out
        assert forward_code == 0, forward_out

    def test_bare_name_added_correct_at_head_is_not_judged_at_the_base(
        self, tmp_path: Path
    ) -> None:
        # The author fixes a bare cite in the branch that moved the lines;
        # the new numbers are right at HEAD. At the merge base, lines 6-7
        # hold other distinctive text that the same insertion moved, so a
        # base comparison would wrongly call the corrected cite stale.
        bare = TARGET.rsplit("/", 1)[1]
        base_content = TARGET_CONTENT + "\nALPHA_VALUE = 10\nBETA_VALUE = 20\n"
        root = _repo(tmp_path)
        _git(root, "checkout", "-q", "main")
        _commit_file(root, TARGET, base_content)
        _commit_file(root, DOC, f"See {bare}:3-4 for the helper.\n")
        _git(root, "checkout", "-q", "-B", "feature")
        _commit_file(root, TARGET, "# one\n# two\n# three\n" + base_content)
        _commit_file(root, DOC, f"See {bare}:6-7 for the helper.\n")

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 1 inbound citation" in out

    def test_ambiguous_bare_name_is_skipped(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        bare = TARGET.rsplit("/", 1)[1]
        _git(root, "checkout", "-q", "main")
        _commit_file(root, f"other/{bare}", "X = 1\n")
        _commit_file(root, DOC, f"The helper `magic_token` is at {bare}:3.\n")
        _git(root, "checkout", "-q", "-B", "feature")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 0 inbound citation" in out


class TestScopeAndExemptions:
    def test_reasoned_ignore_marker_exempts_the_line(self, tmp_path: Path) -> None:
        marker = "<!-- citation-freshness: ignore -- illustrative pointer -->\n"
        root = _repo_with_doc(tmp_path, marker + ANCHORED)
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 0, out

    def test_historical_citing_file_is_exempt(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED, ".project-toolkit/retrospective/r.md")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 0 inbound citation" in out

    def test_citation_stale_at_the_merge_base_does_not_block(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, f"The helper `magic_token` lives at {TARGET}:5.\n")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "1 already stale at the merge base" in out

    def test_added_full_path_line_is_left_to_the_forward_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        (root / DOC).parent.mkdir(parents=True)
        (root / DOC).write_text(ANCHORED, encoding="utf-8")
        _commit_file(root, TARGET, INSERTED_ABOVE)

        code, out = _run_reverse(root)
        forward_code, forward_out = _run(root, capsys)

        assert code == 0, out
        assert forward_code == 1, forward_out

    def test_branch_with_no_changed_cited_file_examines_nothing(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)
        _commit_file(root, "notes.txt", "unrelated\n")

        code, out = _run_reverse(root)

        assert code == 0, out
        assert "examined 0 inbound citation" in out

    def test_unresolvable_base_ref_is_a_config_error(self, tmp_path: Path) -> None:
        root = _repo_with_doc(tmp_path, ANCHORED)

        code, out = _run_reverse(root, base="no-such-ref")

        assert code == 2, out


class TestPrePrWiring:
    def test_reverse_pass_is_a_registered_pre_pr_gate(self) -> None:
        from scripts.validation import pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]

        assert "Citation Freshness (reverse pass)" in labels


def test_range_boundaries_move_even_when_an_anchor_stays_inside(tmp_path: Path) -> None:
    """A growing helper shifts both cited boundaries but retains its name."""
    base = "def magic_token():\n    begin_value = 1\n    return begin_value\n"
    root = _repo_with_doc(tmp_path, f"The `magic_token` helper lives at {TARGET}:1-3.\n")
    _git(root, "checkout", "-q", "main")
    _commit_file(root, TARGET, base)
    _git(root, "checkout", "-q", "-B", "feature")
    head = "# inserted above\n" + base.replace("    return", "    extra_value = 2\n    return")
    _commit_file(root, TARGET, head)

    code, output = _run_reverse(root)

    assert code == 1, output
    assert f"suggested citation {TARGET}:2-5" in output


def test_rewording_the_citing_line_retains_an_existing_bare_citation(tmp_path: Path) -> None:
    """Reworded prose must not hide drift in a citation kept verbatim."""
    name = TARGET.rsplit("/", 1)[-1]
    root = _repo_with_doc(tmp_path, f"The `magic_token` helper lives at {name}:3-4.\n")
    _commit_file(root, TARGET, INSERTED_ABOVE)
    _commit_file(root, DOC, f"The existing `magic_token` helper lives at {name}:3-4.\n")

    code, output = _run_reverse(root)

    assert code == 1, output
    assert f"suggested citation {TARGET}:6-7" in output
