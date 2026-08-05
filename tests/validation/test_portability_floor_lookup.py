"""Tests for the two ways the committed floor could be made to look absent.

The guard reads its floor out of git. That makes every answer git gives it a
place to attack, and the dangerous answer is not an error but a shrug: "nothing
is tracked there." A shrug is indistinguishable from a genuinely new baseline,
so anything that can manufacture one erases the floor without tripping a single
error path. Two such levers existed. HEAD could be pointed at a branch nobody
had created, which fails the same way an unborn repository does. And the path
could be spelled with different case in a parent directory, which git matched
case-sensitively while the filesystem underneath did not.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation import portability_floor
from scripts.validation.portability_floor import (
    Sections,
    read_previous_sections,
)
from scripts.validation.portability_git import GIT_TIMEOUT_RETURN_CODE, tracked_blob


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    (root / "scripts" / "validation").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    return root


def _commit_baseline(root: Path, count: int) -> Path:
    path = root / "scripts" / "validation" / "b.json"
    path.write_text(json.dumps({"_comment": "x", "files": {"a.md": count}}), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return path


def test_committed_object_timeout_names_the_failed_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    path = root / "scripts" / "validation" / "b.json"
    monkeypatch.setattr(
        portability_floor,
        "committed_blob",
        lambda *_args: ("deadbeef", None),
    )
    monkeypatch.setattr(
        portability_floor,
        "run_git",
        lambda *_args: subprocess.CompletedProcess(
            ["git", "cat-file"],
            GIT_TIMEOUT_RETURN_CODE,
            stdout=b"",
            stderr=b"git command timed out after 30s",
        ),
    )

    previous, problem = read_previous_sections(root, path)

    assert previous is None
    assert problem is not None and "reading the committed baseline object" in problem


class TestAnUnresolvableHeadIsNotProofOfAnEmptyRepository:
    """`rev-parse --verify --quiet HEAD` answers identically in two states.

    A repository nobody has committed to yet and a repository whose HEAD names
    a deleted branch both return non-zero with nothing on stdout. Only one of
    them has no floor. Reading the shared answer as "no commits" let a single
    edit inside `.git` promote the working tree copy to sole witness, which is
    the copy the run asking for the shrink can rewrite first.
    """

    def test_head_pointing_at_a_deleted_branch_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(root, 4)
        path.write_text(json.dumps({"_comment": "x", "files": {"a.md": 1}}), encoding="utf-8")
        (root / ".git" / "HEAD").write_text("ref: refs/heads/nope\n", encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None
        assert "refs" in problem

    def test_an_unborn_repository_still_reports_no_floor(self, tmp_path: Path) -> None:
        """The one honest way to have nothing committed must keep working, or
        the first baseline in a fresh checkout could never be written."""
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        path.write_text(json.dumps({"_comment": "x", "files": {"a.md": 1}}), encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 1}}

    def test_a_healthy_repository_still_reads_the_committed_floor(
        self, tmp_path: Path
    ) -> None:
        """The control. Without it the two tests above pass on a guard that
        refuses everything, which would prove nothing about the attack."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, 4)
        path.write_text(json.dumps({"_comment": "x", "files": {"a.md": 1}}), encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 4}}


class TestCaseIsResolvedAgainstTheTreeRatherThanAPathspec:
    """Handing git the parent as a pathspec matched it case-sensitively.

    The leaf was then compared case-insensitively, so the two halves of one
    lookup disagreed. A parent spelled `Scripts` listed nothing, and nothing
    reads as "no committed copy" while a case-insensitive filesystem still
    opens the real file underneath. Walking the tree one component at a time
    puts both halves under the same rule.
    """

    def test_a_parent_differing_only_by_case_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        _commit_baseline(root, 4)

        blob, problem = tracked_blob(root, Path("Scripts/validation/b.json"))

        assert blob is None
        assert problem is not None
        assert "case" in problem

    def test_the_exact_spelling_is_still_found(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        _commit_baseline(root, 4)

        blob, problem = tracked_blob(root, Path("scripts/validation/b.json"))

        assert problem is None
        assert blob is not None

    def test_an_exact_match_wins_over_a_case_twin_beside_it(self, tmp_path: Path) -> None:
        """Deciding on the first case-insensitive hit refused a path git tracks
        exactly whenever a twin sorted ahead of it. Every candidate is collected
        before anything is decided, so the exact one is available to win."""
        root = _repo(tmp_path)
        for name, count in (("B.json", 9), ("b.json", 4)):
            (root / "scripts" / "validation" / name).write_text(
                json.dumps({"_comment": "x", "files": {"a.md": count}}), encoding="utf-8"
            )
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "twins")

        blob, problem = tracked_blob(root, Path("scripts/validation/b.json"))

        assert problem is None
        assert blob is not None
        body = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", blob],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        assert json.loads(body)["files"] == {"a.md": 4}

    def test_case_twins_with_no_exact_match_are_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        for name in ("B.json", "b.json"):
            (root / "scripts" / "validation" / name).write_text(
                json.dumps({"_comment": "x", "files": {"a.md": 4}}), encoding="utf-8"
            )
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "twins")

        blob, problem = tracked_blob(root, Path("scripts/validation/C.json"))

        assert blob is None
        assert problem is None

    def test_a_path_git_tracks_as_a_directory_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        _commit_baseline(root, 4)

        blob, problem = tracked_blob(root, Path("scripts/validation"))

        assert blob is None
        assert problem is not None
        assert "regular file" in problem

    def test_a_parent_that_is_a_file_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        _commit_baseline(root, 4)

        blob, problem = tracked_blob(root, Path("scripts/validation/b.json/nested.json"))

        assert blob is None
        assert problem is not None
        assert "directory" in problem

    def test_an_untracked_path_is_still_reported_absent(self, tmp_path: Path) -> None:
        """The shrug has to survive, because a genuinely new baseline produces
        it. A guard that refused here could never record a new section."""
        root = _repo(tmp_path)
        _commit_baseline(root, 4)

        blob, problem = tracked_blob(root, Path("scripts/validation/brand-new.json"))

        assert blob is None
        assert problem is None


class TestAFloorIsBuiltOnlyFromJsonIntegers:
    """`int()` reads shapes that are not integers, and reads them downward.

    Every one of these arrives as committed JSON, so the attacker's cost is a
    diff that changes punctuation rather than a number. `false` reads as a floor
    of nothing, and `4.9` reads as one less than it says. Both are refusals now.
    """

    @staticmethod
    def _floor(root: Path, payload: object) -> tuple[Sections | None, str | None]:
        path = root / "scripts" / "validation" / "b.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "seed")
        return read_previous_sections(root, path)

    def test_a_boolean_count_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": False}})

        assert sections is None
        assert problem is not None and "not an integer" in problem

    def test_a_fractional_count_is_refused_rather_than_truncated(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": 4.9}})

        assert sections is None
        assert problem is not None and "not an integer" in problem

    def test_a_numeric_string_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": "3"}})

        assert sections is None
        assert problem is not None and "not an integer" in problem

    def test_a_negative_count_is_refused(self, tmp_path: Path) -> None:
        """No scan can produce one, so it is corruption or an attempt."""
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": -1}})

        assert sections is None
        assert problem is not None and "negative" in problem

    def test_a_genuine_integer_still_reads_as_the_floor(self, tmp_path: Path) -> None:
        """The control. Without it the refusals above could be unconditional."""
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": 4}})

        assert problem is None
        assert sections == {"files": {"a.md": 4}}

    def test_zero_is_a_floor_and_not_an_absence(self, tmp_path: Path) -> None:
        """Zero is falsy, so a truthiness test here would read it as missing."""
        root = _repo(tmp_path)

        sections, problem = self._floor(root, {"files": {"a.md": 0}})

        assert problem is None
        assert sections == {"files": {"a.md": 0}}
