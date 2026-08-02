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

from scripts.validation.portability_baseline import (  # noqa: E402
    read_previous_sections,
    refuse_symlinked_baseline,
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
        path = _commit_baseline(
            root, {"_comment": "why", "_meta": {"tool": "x"}, "files": {"a.md": 1}}
        )

        previous, problem = read_previous_sections(root, path)

        assert problem is None
        assert previous == {"files": {"a.md": 1}}


class TestTheWriteCannotBeRedirectedOffThePathGitTracks:
    """The leaf being a regular file proves nothing about where it resolves."""

    def test_a_symlinked_parent_directory_is_refused(self, tmp_path: Path) -> None:
        """Isolates the chain walk: the target stays inside the repository, so
        the escape check cannot be what catches this."""
        root = _repo(tmp_path)
        (root / "real").mkdir()
        (root / "scripts" / "validation" / "sub").symlink_to(
            root / "real", target_is_directory=True
        )
        path = root / "scripts" / "validation" / "sub" / "b.json"

        assert refuse_symlinked_baseline(root, path)

    def test_a_destination_that_climbs_out_of_the_repository_is_refused(
        self, tmp_path: Path
    ) -> None:
        """Isolates the escape check: nothing on this path is a symlink."""
        root = _repo(tmp_path)
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        path = root / ".." / "elsewhere" / "b.json"

        assert refuse_symlinked_baseline(root, path)

    def test_a_symlinked_parent_does_not_get_written_through(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        (root / "real").mkdir()
        victim = root / "real" / "b.json"
        victim.write_text("DO NOT OVERWRITE", encoding="utf-8")
        (root / "scripts" / "validation" / "sub").symlink_to(
            root / "real", target_is_directory=True
        )
        path = root / "scripts" / "validation" / "sub" / "b.json"

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, False
        )

        assert rc == 2
        assert victim.read_text(encoding="utf-8") == "DO NOT OVERWRITE"

    def test_an_ordinary_nested_path_inside_the_repository_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """The refusal must not fire on every path with a parent directory."""
        root = _repo(tmp_path)
        nested = root / "scripts" / "validation" / "sub"
        nested.mkdir()

        assert not refuse_symlinked_baseline(root, nested / "b.json")

    def test_the_repository_root_itself_terminates_the_walk(
        self, tmp_path: Path
    ) -> None:
        """A symlink above the root is somebody else's problem, not the ratchet's.

        Walking past the root would make the refusal depend on where the
        checkout happens to live, which is not something a contributor can fix.
        """
        root = _repo(tmp_path)

        assert not refuse_symlinked_baseline(root, root / "b.json")


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
