"""Tests for the ways git itself can be made to answer wrongly about a baseline.

Every case here is a command that succeeds and returns something false rather
than one that fails. `ls-tree` applies the current directory as a prefix to any
tree-ish and prints nothing when that prefix does not exist inside the subtree.
It reports a symlink as a blob. It decodes names lossily. Git serves whatever a
`refs/replace` entry points at. And a repository whose refs are all gone still
holds its commits. Each one produced an empty or wrong answer that the walk
above read as "no committed baseline exists", which is the one reading that
removes the floor entirely.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation import portability_floor
from scripts.validation.portability_floor import read_previous_sections
from scripts.validation.portability_git import tree_entries, was_recorded

pytestmark = pytest.mark.unit

HIGH = {"files": {"victim": 5}}
LOW = {"files": {"victim": 0}}
REL = Path("scripts/validation/baseline.json")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo(root: Path, *, inner: str = "") -> Path:
    """Create a repository, returning the directory a checker would be pointed at."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True
    )
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    base = root / inner if inner else root
    (base / REL.parent).mkdir(parents=True, exist_ok=True)
    return base


def _commit(top: Path, base: Path, payload: Mapping[str, object]) -> None:
    (base / REL).write_text(json.dumps(payload), encoding="utf-8")
    _git(top, "add", "-A")
    _git(top, "commit", "-qm", "baseline")


class TestTheFloorSurvivesWhereGitAnswersWithSilence:
    """`ls-tree` prints nothing for a tree-ish it cannot reach under its prefix."""

    def test_a_checkout_below_the_git_top_level_still_reads_the_floor(
        self, tmp_path: Path
    ) -> None:
        """The prefix applies to every tree-ish, not only to HEAD.

        Descending into a subtree re-applies it, finds nothing, and exits 0.
        """
        base = _repo(tmp_path / "repo", inner="pkg")
        top = tmp_path / "repo"
        _commit(top, base, HIGH)
        (base / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(base, base / REL)

        assert problem is None
        assert previous == HIGH

    def test_the_top_level_case_still_reads_the_floor(self, tmp_path: Path) -> None:
        """The control. `--full-tree` must not break the layout that worked."""
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == HIGH

    def test_an_empty_listing_for_a_subtree_is_a_refusal(self, tmp_path: Path) -> None:
        """Git stores no empty subtree, so nothing there means the lookup failed."""
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        empty_tree = _git(top, "hash-object", "-t", "tree", "--stdin", "-w").stdout.strip()

        entries, problem = tree_entries(top, empty_tree)

        assert entries is None
        assert problem is not None and "no stored tree object can be" in problem

    def test_an_empty_root_tree_is_allowed(self, tmp_path: Path) -> None:
        """The control. An empty commit has an empty root tree, honestly."""
        top = _repo(tmp_path / "repo")
        _git(top, "commit", "-qm", "empty", "--allow-empty")

        entries, problem = tree_entries(top, "HEAD", may_be_empty=True)

        assert problem is None
        assert entries == []


class TestTheFloorIsReadFromHistoryAndNotFromASubstitute:
    """A `refs/replace` entry lives in `.git`, is not pushed, and leaves no diff."""

    def test_a_replacement_ref_does_not_become_the_floor(self, tmp_path: Path) -> None:
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        real = _git(top, "rev-parse", "HEAD").stdout.strip()

        _git(top, "checkout", "-q", "--orphan", "forged")
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")
        _git(top, "add", "-A")
        _git(top, "commit", "-qm", "forged")
        forged = _git(top, "rev-parse", "HEAD").stdout.strip()
        _git(top, "checkout", "-q", "main")
        _git(top, "replace", real, forged)
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == HIGH

    def test_the_same_repository_without_the_replacement_reads_the_same_floor(
        self, tmp_path: Path
    ) -> None:
        """The control. The refusal above must come from the ref, not the setup."""
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == HIGH


class TestNoRefsIsNotProofNothingWasCommitted:
    """Deleting every ref leaves the commits in the object database."""

    def test_a_repository_whose_refs_were_deleted_is_refused(self, tmp_path: Path) -> None:
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        _git(top, "symbolic-ref", "HEAD", "refs/heads/gone")
        for ref in _git(top, "for-each-ref", "--format=%(refname)").stdout.split():
            _git(top, "update-ref", "-d", ref)
        packed = top / ".git" / "packed-refs"
        if packed.exists():
            packed.unlink()
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert previous is None
        assert problem is not None and "object database still holds commits" in problem

    def test_a_repository_that_was_never_committed_to_has_no_floor(
        self, tmp_path: Path
    ) -> None:
        """The control. Without it the refusal above could be unconditional."""
        top = _repo(tmp_path / "repo")
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == LOW


class TestTheCommittedBaselineMustBeARegularFile:
    """Git records a symlink as a blob holding the text of its target."""

    def test_a_committed_symlink_is_refused(self, tmp_path: Path) -> None:
        """Its blob is a pathname, so the floor would parse a different file."""
        top = _repo(tmp_path / "repo")
        os.symlink(json.dumps(LOW), top / REL)
        _git(top, "add", "-A")
        _git(top, "commit", "-qm", "symlink baseline")
        (top / REL).unlink()
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert previous is None
        assert problem is not None and "mode 120000" in problem

    def test_an_executable_baseline_is_still_read(self, tmp_path: Path) -> None:
        """The control. The refusal is about symlinks, not about the mode bit."""
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        _git(top, "update-index", "--chmod=+x", str(REL))
        _git(top, "commit", "-qm", "executable")
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == HIGH


class TestATreeNameIsDecodedTheWayThePathIs:
    """`"replace"` maps invalid bytes to U+FFFD; argv carries surrogate escapes."""

    def test_a_non_utf8_committed_name_still_matches(self, tmp_path: Path) -> None:
        top = _repo(tmp_path / "repo")
        rel = Path(os.fsdecode(b"scripts/validation/baseline-\xff.json"))
        (top / rel).write_bytes(json.dumps(HIGH).encode())
        _git(top, "add", "-A")
        _git(top, "commit", "-qm", "odd name")
        (top / rel).write_bytes(json.dumps(LOW).encode())

        previous, problem = read_previous_sections(top, top / rel)

        assert problem is None
        assert previous == HIGH

    def test_an_ascii_committed_name_still_matches(self, tmp_path: Path) -> None:
        """The control. The match above must not come from a loosened compare."""
        top = _repo(tmp_path / "repo")
        _commit(top, top, HIGH)
        (top / REL).write_text(json.dumps(LOW), encoding="utf-8")

        previous, problem = read_previous_sections(top, top / REL)

        assert problem is None
        assert previous == HIGH


class TestAPathThatCannotBeResolvedIsNotProofNothingWasRecorded:
    """Two failures of the same expression mean opposite things.

    `was_recorded` resolves the baseline and makes it relative to the root.
    `ValueError` means the resolve worked and the answer is "elsewhere", which
    this repository's history genuinely does not record. `OSError` means the
    resolve never happened, so nothing was learned. Both returned `False`, and
    `read_previous_sections` reads `False` as "no debt has ever been recorded"
    and proceeds, so an unanswered question granted permission.

    On CPython 3.14 and Linux the `OSError` arm is defensive rather than
    reachable: non-strict `Path.resolve()` swallows ELOOP, ENAMETOOLONG and
    EACCES, all three checked. It is raised here rather than induced, and the
    test claims only that the contract holds, not that a caller can trip it.
    Other platforms and older interpreters do raise, and the docstring on the
    function has promised `None` for an unanswerable resolve throughout.
    """

    def test_a_path_outside_the_repository_is_recorded_nowhere_in_it(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path / "repo")
        outside = tmp_path / "elsewhere" / "baseline.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}\n")

        assert was_recorded(root, outside) is False

    def test_an_unresolvable_path_answers_unknown_and_not_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _repo(tmp_path / "repo")
        baseline = root / REL
        real = Path.resolve

        def refuse(self: Path, strict: bool = False) -> Path:
            if self == baseline:
                raise OSError(5, "Input/output error")
            return real(self, strict)

        monkeypatch.setattr(Path, "resolve", refuse)
        assert was_recorded(root, baseline) is None

    def test_the_control_resolves_and_answers(self, tmp_path: Path) -> None:
        """Without the induced failure the same call returns a real verdict."""
        root = _repo(tmp_path / "repo")
        baseline = root / REL
        baseline.write_text("{}\n")

        assert was_recorded(root, baseline) is False

        _commit(root, root, {"files": {"a/b.py": 5}})
        assert was_recorded(root, baseline) is True

    def test_the_caller_refuses_before_it_ever_asks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Order, not the return value. `False` was never reachable from here.

        `read_previous_sections` reads the committed copy first, and that path
        already separated the two failures correctly: it refuses an OSError and
        treats a ValueError as "git tracks nothing here". So the conflation
        below it could not be reached through any checker, and calling it a live
        fail-open overstates it. What is pinned is the ordering that makes that
        true, because a refactor that consulted history first would open the
        hole for real, and no assertion on a return value would notice.
        """
        root = _repo(tmp_path / "repo")
        baseline = root / REL
        real = Path.resolve
        asked = False

        def refuse(self: Path, strict: bool = False) -> Path:
            if self == baseline:
                raise OSError(5, "Input/output error")
            return real(self, strict)

        def spy(*args: object, **kwargs: object) -> bool | None:
            nonlocal asked
            asked = True
            return False

        monkeypatch.setattr(Path, "resolve", refuse)
        monkeypatch.setattr(portability_floor, "was_recorded", spy)
        sections, problem = read_previous_sections(root, baseline)

        assert sections is None
        assert problem is not None
        assert not asked, "history was consulted before the committed copy refused"
