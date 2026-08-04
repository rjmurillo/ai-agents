"""Tests for where a baseline write is allowed to land.

The comparison the guard runs is only worth anything if the file it compares
is the file git tracks. A symlink anywhere on the way down, or a destination
that climbs out of the tree, redirects the write while leaving the leaf
looking ordinary. These tests attack the destination rather than the numbers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.portability_baseline import (
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

    def test_a_link_to_the_root_is_still_a_link(self, tmp_path: Path) -> None:
        """Reaching the root ends the walk. It does not excuse the step that got
        there.

        A directory named `scripts` pointing at the repository root resolves to
        the root, so the walk used to stop clean without ever asking whether
        that component was a symlink. The write still lands somewhere other
        than the path git tracks under that name.
        """
        root = tmp_path / "repo"
        root.mkdir()
        _git(root, "init", "-q")
        (root / "validation").mkdir()
        (root / "scripts").symlink_to(root, target_is_directory=True)
        path = root / "scripts" / "validation" / "b.json"

        assert path.resolve() != (root / "scripts" / "validation" / "b.json")
        assert refuse_symlinked_baseline(root, path)

    def test_a_real_directory_that_sits_directly_under_the_root_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """The control for the case above: the same shape without the link.

        Without this, a refusal that fired on every path whose parent chain
        reaches the root would pass the test above for the wrong reason.
        """
        root = tmp_path / "repo"
        root.mkdir()
        _git(root, "init", "-q")
        (root / "scripts" / "validation").mkdir(parents=True)
        path = root / "scripts" / "validation" / "b.json"

        assert not refuse_symlinked_baseline(root, path)

    def test_a_link_to_the_root_does_not_get_written_through(
        self, tmp_path: Path
    ) -> None:
        """The victim is valid, matching JSON on purpose.

        Corrupt bytes there would make the floor read refuse and the write stop
        for a reason that has nothing to do with the link, leaving this test
        passing whether or not the link is caught.
        """
        root = tmp_path / "repo"
        root.mkdir()
        _git(root, "init", "-q")
        (root / "validation").mkdir()
        victim = root / "validation" / "b.json"
        victim.write_text(
            json.dumps({"_comment": "not the ratchet's file", "files": {"a.md": 1}}),
            encoding="utf-8",
        )
        original = victim.read_text(encoding="utf-8")
        (root / "scripts").symlink_to(root, target_is_directory=True)
        path = root / "scripts" / "validation" / "b.json"

        rc = write_baseline_json(
            root, path, {"files": {"a.md": 1}}, {"files": {"a.md": 1}}, UNIT, False
        )

        assert rc == 2
        assert victim.read_text(encoding="utf-8") == original

    def test_parent_step_does_not_hide_an_intermediate_symlink(
        self, tmp_path: Path
    ) -> None:
        """The symlink walk must catch `link/../file` before any write."""
        root = _repo(tmp_path)
        (root / "target" / "a" / "b").mkdir(parents=True)
        (root / "target" / "a" / "victim.json").write_text("{}", encoding="utf-8")
        (root / "link").symlink_to(root / "target" / "a" / "b")
        path = root / "link" / ".." / "victim.json"

        assert refuse_symlinked_baseline(root, path)
