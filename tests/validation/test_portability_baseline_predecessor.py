"""Tests for the witnesses the baseline guard consults before it overwrites.

The guard's whole job is to make the replacement argue with its predecessor.
That only works if the predecessor cannot be edited by the same run that wants
the argument to go a particular way, so these tests attack the witness rather
than the comparison: empty it, corrupt it, hide a section in it, or move the
destination out from under it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.portability_baseline import (
    read_previous_sections,
    write_baseline_json,
)

UNIT = "skill files"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "validation").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    return root


def _commit_baseline(root: Path, payload: object) -> Path:
    path = root / "scripts" / "validation" / "b.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return path


class TestTheCommittedCopyIsTheFloor:
    """A predecessor that lives only in the working tree is not a witness.

    Every one of these starts from a baseline that HEAD records honestly and
    then damages the copy on disk, which is the copy the run doing the damage
    can reach. The committed object is what has to decide the outcome.
    """

    def test_an_emptied_worktree_copy_does_not_forgive_a_shrink(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4, "b.md": 3}})
        path.write_text("{}", encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 4, "b.md": 3}}

    def test_an_emptied_worktree_copy_cannot_launder_a_wipe_through_the_write(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4, "b.md": 3}})
        path.write_text("{}", encoding="utf-8")

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, False
        )

        assert rc == 2
        assert path.read_text(encoding="utf-8") == "{}"

    def test_a_lowered_worktree_copy_loses_to_the_committed_counts(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 9}})
        path.write_text(json.dumps({"files": {"a.md": 1}}), encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 9}}

    def test_honest_progress_on_disk_still_outranks_a_stale_commit(
        self, tmp_path: Path
    ) -> None:
        """The floor raises the count, it never lowers one.

        A contributor who genuinely recorded more debt since the last commit
        must not have that reading thrown away in favour of an older, smaller
        one, or the guard would forgive the difference.
        """
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 2}})
        path.write_text(json.dumps({"files": {"a.md": 7, "b.md": 1}}), encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 7, "b.md": 1}}

    def test_a_deliberate_reduction_still_has_its_documented_way_through(
        self, tmp_path: Path
    ) -> None:
        """The floor must not turn the escape hatch into a dead end."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4, "b.md": 3}})

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, True
        )

        assert rc == 0
        assert json.loads(path.read_text(encoding="utf-8")) == {"files": {"a.md": 1}}

    def test_a_baseline_with_no_commit_behind_it_is_still_writable(
        self, tmp_path: Path
    ) -> None:
        """A genuinely new baseline has no floor, and must not be refused."""
        root = _repo(tmp_path)
        _commit_baseline(root, {"files": {"a.md": 1}})
        fresh = root / "scripts" / "validation" / "new.json"

        rc = write_baseline_json(
            root, fresh, {"files": {"x.md": 2}}, {"files": {"x.md": 2}}, UNIT, False
        )

        assert rc == 0
        assert json.loads(fresh.read_text(encoding="utf-8")) == {"files": {"x.md": 2}}

    def test_a_corrupt_committed_copy_fails_closed(self, tmp_path: Path) -> None:
        """An unreadable floor is a mystery, and a mystery is not a licence."""
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        path.write_text("{ this is not json", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "seed")
        path.write_text(json.dumps({"files": {}}), encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None
        assert "committed copy" in problem


class TestSectionsNobodyGuardsAreRefusedByName:
    """The replacement is rebuilt from the scan, so an unknown section is not
    merely uncompared, it is deleted by the write that ignores it."""

    def test_an_unknown_count_section_refuses_the_read(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(
            root, {"files": {"a.md": 1}, "ghost_files": {"g.md": 4}}
        )

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None
        assert "ghost_files" in problem

    def test_an_unknown_count_section_is_not_silently_overwritten(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(
            root, {"files": {"a.md": 1}, "ghost_files": {"g.md": 4}}
        )

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, False
        )

        assert rc == 2
        assert json.loads(path.read_text(encoding="utf-8"))["ghost_files"] == {"g.md": 4}

    def test_the_escape_hatch_does_not_authorise_deleting_a_section(
        self, tmp_path: Path
    ) -> None:
        """`--allow-baseline-shrink` forgives a smaller count, not a lost section."""
        root = _repo(tmp_path)
        path = _commit_baseline(
            root, {"files": {"a.md": 1}, "ghost_files": {"g.md": 4}}
        )

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, True
        )

        assert rc == 2
        assert json.loads(path.read_text(encoding="utf-8"))["ghost_files"] == {"g.md": 4}

    def test_a_known_section_is_not_mistaken_for_an_unknown_one(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _commit_baseline(
            root, {"files": {"a.md": 1}, "marker_files": {"m.md": 2}}
        )

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 1}, "marker_files": {"m.md": 2}}

    def test_metadata_that_is_not_a_count_does_not_trip_the_refusal(
        self, tmp_path: Path
    ) -> None:
        """`_comment` is a string and every real baseline carries one."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"_comment": "why", "files": {"a.md": 1}})

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 1}}

    @pytest.mark.parametrize(
        "payload",
        [
            {"tool": "x"},
            {"schema_version": 2},
            {"enabled": True},
            {},
        ],
        ids=["strings", "integers", "booleans", "empty"],
    )
    def test_an_unknown_object_is_refused_whatever_it_holds(
        self, tmp_path: Path, payload: dict[str, object]
    ) -> None:
        """The write rebuilds the payload from the scan, so every unknown object
        is erased by it, not only the ones whose values are integers. A guard
        that only noticed integers would let the next author pick another shape,
        and an empty object is the cheapest shape of all."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"_meta": payload, "files": {"a.md": 1}})

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None
        assert "_meta" in problem




@pytest.mark.parametrize("allow_shrink", [False, True])
def test_a_healthy_rewrite_is_unaffected_by_any_of_it(
    tmp_path: Path, allow_shrink: bool
) -> None:
    """None of the new refusals may cost an honest regeneration."""
    root = _repo(tmp_path)
    path = _commit_baseline(root, {"files": {"a.md": 2, "b.md": 3}})
    same = {"files": {"a.md": 2, "b.md": 3}}

    rc = write_baseline_json(root, path, same, same, UNIT, allow_shrink)

    assert rc == 0
    assert json.loads(path.read_text(encoding="utf-8")) == same


class TestALookupThatFailsIsNotAnAbsentFloor:
    """`git show` returning nonzero used to mean "no committed floor".

    That reading makes the floor optional: anything an attacker can do to break
    the lookup removes the only witness the guard cannot reach. Absence has to
    be proven by git answering, not inferred from git failing.
    """

    def test_a_repository_with_no_git_directory_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The cheapest way to silence the floor is to make git itself fail."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4}})
        path.write_text("{}", encoding="utf-8")
        (root / ".git").rename(root.parent / "git-elsewhere")

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None

    def test_a_corrupt_object_store_is_refused(self, tmp_path: Path) -> None:
        """A blob git lists but cannot read is a failure, not an empty floor."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4}})
        path.write_text("{}", encoding="utf-8")
        objects = root / ".git" / "objects"
        for blob in objects.rglob("*"):
            if blob.is_file() and blob.parent.name != "info":
                blob.unlink(missing_ok=True)

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None

    def test_a_baseline_git_tracks_under_another_case_is_refused(
        self, tmp_path: Path
    ) -> None:
        """On a case-insensitive filesystem the pathspec misses and the floor
        would vanish, even though the same bytes are on disk."""
        root = _repo(tmp_path)
        _commit_baseline(root, {"files": {"a.md": 4}})

        previous, problem = read_previous_sections(
            root, root / "scripts" / "validation" / "B.json"
        )

        assert previous is None
        assert problem is not None
        assert "case" in problem

    def test_a_directory_where_the_baseline_should_be_is_refused(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        nested = root / "scripts" / "validation" / "b.json"
        nested.mkdir()
        (nested / "inner.txt").write_text("x", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "seed")

        previous, problem = read_previous_sections(root, nested)

        assert previous is None
        assert problem is not None

    def test_a_genuinely_new_baseline_still_has_no_floor(
        self, tmp_path: Path
    ) -> None:
        """The refusals above are only correct if this stays permitted."""
        root = _repo(tmp_path)
        _commit_baseline(root, {"files": {"a.md": 4}})
        fresh = root / "scripts" / "validation" / "brand-new.json"
        fresh.write_text('{"files": {"c.md": 1}}', encoding="utf-8")

        previous, problem = read_previous_sections(root, fresh)

        assert problem is None
        assert previous == {"files": {"c.md": 1}}

    def test_a_repository_with_no_commits_has_no_floor(self, tmp_path: Path) -> None:
        """No HEAD is the one honest way to have nothing committed."""
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        path.write_text('{"files": {"a.md": 1}}', encoding="utf-8")

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 1}}

    def test_a_baseline_outside_the_repository_has_no_floor(
        self, tmp_path: Path
    ) -> None:
        """A direct library call can still reach this; no checker CLI can.

        All three checkers reject an out-of-root `--baseline` before they get
        here, so this pins the branch for library callers rather than for the
        CLI. It is honest for them: git tracks nothing outside the work tree,
        so there is genuinely no floor to apply.
        """
        root = _repo(tmp_path)
        _commit_baseline(root, {"files": {"a.md": 4}})
        outside = tmp_path / "outside.json"
        outside.write_text('{"files": {"z.md": 1}}', encoding="utf-8")

        previous, problem = read_previous_sections(root, outside)

        assert problem is None
        assert previous == {"files": {"z.md": 1}}

    def test_a_listed_blob_that_cannot_be_read_is_refused(
        self, tmp_path: Path
    ) -> None:
        """Deleting every object makes the listing fail first, which leaves the
        read itself unproven. Removing only the blob keeps the tree intact, so
        git still names the baseline and then cannot hand it over."""
        root = _repo(tmp_path)
        path = _commit_baseline(root, {"files": {"a.md": 4}})
        path.write_text("{}", encoding="utf-8")
        blob = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD:scripts/validation/b.json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
        (root / ".git" / "objects" / blob[:2] / blob[2:]).unlink()

        previous, problem = read_previous_sections(root, path)

        assert previous is None
        assert problem is not None
