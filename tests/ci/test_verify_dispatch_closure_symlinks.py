"""Symlinked directories on one side, both sides, or leaving the tree (issue #6722).

ADR-119 made `.claude/skills/<name>` a link into `src/claude/skills`. The base ref
and the head must resolve such a path the same way: a link on either side is
followed to the bytes it names, and a link that leaves the tree is never followed.
Each case runs with a head SHA, as CI does, and with a work-tree head, as a local
run does.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import (
    DEMO_LINK,
    DEMO_TARGET,
    HELPER,
    REPO_ROOT,
    VERIFIER,
    git,
    link_demo_skill,
    rev,
)

TARGET_HELPER = f"{DEMO_TARGET}/scripts/helper.py"
MODES = pytest.mark.parametrize("with_sha", [True, False], ids=["head-sha", "work-tree"])


def _commit(head: Path, message: str) -> str:
    git(head, "add", "-A")
    git(head, "commit", "-q", "-m", message)
    return rev(head)


def _verify(base: Path, head: Path, with_sha: bool) -> vdc.Report:
    sha = rev(head) if with_sha else None
    return vdc.verify(base, head, "HEAD", head_sha=sha)


def _relink(head: Path, target: str) -> None:
    link = head / DEMO_LINK
    if link.is_symlink():
        link.unlink()
    else:
        shutil.rmtree(link)
    link.symlink_to(target)


def _outside_copy(head: Path, base: Path, body: bytes | None = None) -> str:
    """A copy of the demo skill outside both trees; returns the link text that reaches it."""
    outside = head.parent / "outside"
    shutil.copytree(base / ".claude/skills/demo", outside, symlinks=False, dirs_exist_ok=True)
    if body is not None:
        (outside / "scripts/helper.py").write_bytes(body)
    return "../../../outside"


@pytest.fixture
def linked_trees(trees: tuple[Path, Path]) -> tuple[Path, Path]:
    base, head = trees
    link_demo_skill(base)
    git(head, "checkout", "--detach", "-q", "--force", rev(base))
    return base, head


class TestLinkInBothRefs:
    @MODES
    def test_the_same_link_in_both_refs_is_clean(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = linked_trees

        report = _verify(base, head, with_sha)

        assert report.clean, report.to_json()
        assert report.examined >= 3

    @MODES
    def test_a_module_imported_through_the_link_joins_the_closure(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        """Before #6722 the gate refused the unpinned link and dropped the import unchecked."""
        base, head = linked_trees
        (head / TARGET_HELPER).write_text("X = 2\n", encoding="utf-8")
        _commit(head, "edit behind the link")

        report = _verify(base, head, with_sha)

        assert report.changed == [TARGET_HELPER]
        assert report.added == []
        assert report.symlinks == []


class TestLinkInTheBaseOnly:
    @MODES
    def test_a_real_head_directory_with_the_same_bytes_is_clean(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = linked_trees
        (head / DEMO_LINK).unlink()
        shutil.copytree(head / DEMO_TARGET, head / DEMO_LINK)
        _commit(head, "replace the link with a copy")

        report = _verify(base, head, with_sha)

        assert report.clean, report.to_json()

    @MODES
    def test_a_real_head_directory_with_other_bytes_is_changed_not_new(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = linked_trees
        (head / DEMO_LINK).unlink()
        shutil.copytree(head / DEMO_TARGET, head / DEMO_LINK)
        (head / HELPER).write_text("X = 3\n", encoding="utf-8")
        _commit(head, "replace the link with an edited copy")

        report = _verify(base, head, with_sha)

        assert report.changed == [HELPER]
        assert report.added == []


class TestLinkInTheHeadOnly:
    @MODES
    def test_a_head_link_to_the_same_bytes_is_a_new_symlink_not_a_new_file(
        self, trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = trees
        link_demo_skill(head)

        report = _verify(base, head, with_sha)

        assert report.symlinks == [DEMO_LINK]
        assert report.added == []
        assert report.changed == []
        assert not report.clean

    @MODES
    def test_a_head_link_to_other_bytes_is_never_followed_and_fails(
        self, trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = trees
        link_demo_skill(head)
        (head / TARGET_HELPER).write_text("X = 4\n", encoding="utf-8")
        _commit(head, "edit behind the new link")

        report = _verify(base, head, with_sha)

        assert report.symlinks == [DEMO_LINK]
        assert TARGET_HELPER not in report.changed
        assert not report.clean


class TestLinkThatLeavesTheTree:
    @MODES
    def test_a_base_link_retargeted_outside_the_tree_fails_closed(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = linked_trees
        _relink(head, _outside_copy(head, base))
        _commit(head, "point the link outside the tree")

        report = _verify(base, head, with_sha)

        assert not report.clean
        assert report.symlinks == [DEMO_LINK]
        assert report.removed == [VERIFIER]

    @MODES
    def test_a_new_head_link_outside_the_tree_fails_closed(
        self, trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = trees
        _relink(head, _outside_copy(head, base))
        _commit(head, "replace the skill with a link outside the tree")

        report = _verify(base, head, with_sha)

        assert not report.clean
        assert report.symlinks == [DEMO_LINK]
        assert report.removed == [VERIFIER]

    @MODES
    def test_an_absolute_head_link_fails_closed(
        self, linked_trees: tuple[Path, Path], with_sha: bool
    ) -> None:
        base, head = linked_trees
        _outside_copy(head, base)
        _relink(head, str(head.parent / "outside"))
        _commit(head, "point the link at an absolute path")

        report = _verify(base, head, with_sha)

        assert not report.clean
        assert report.symlinks == [DEMO_LINK]
        assert report.removed == [VERIFIER]


class TestTheRepositoryClosure:
    def test_modules_behind_the_adr_119_links_join_the_closure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        followed = vdc.verify(REPO_ROOT, REPO_ROOT, "HEAD").examined
        monkeypatch.setattr(vdc._REF_LINKS, "link_table", lambda *_: {})

        refused = vdc.verify(REPO_ROOT, REPO_ROOT, "HEAD").examined

        assert followed > refused


class TestLinkTable:
    def test_lists_each_link_with_its_text(self, linked_trees: tuple[Path, Path]) -> None:
        base, _ = linked_trees

        assert vdc._REF_LINKS.link_table(base, "HEAD") == {
            DEMO_LINK: "../../src/claude/skills/demo"
        }

    def test_a_ref_that_cannot_be_listed_is_empty(self, linked_trees: tuple[Path, Path]) -> None:
        base, _ = linked_trees

        assert vdc._REF_LINKS.link_table(base, "refs/heads/nowhere") == {}

    def test_an_unreadable_link_blob_is_a_configuration_error(
        self, linked_trees: tuple[Path, Path]
    ) -> None:
        base, head = linked_trees
        sha = subprocess.run(
            ["git", "rev-parse", f"HEAD:{DEMO_LINK}"],
            cwd=base,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        (base / ".git/objects" / sha[:2] / sha[2:]).unlink()

        assert vdc._REF_LINKS.link_table(base, "HEAD") is None
        with pytest.raises(vdc.DispatchClosureError, match="symlink"):
            vdc.verify(base, head, "HEAD")


class TestHeadFile:
    def test_a_file_through_an_inside_link_is_read(self, linked_trees: tuple[Path, Path]) -> None:
        _, head = linked_trees

        assert vdc._head_file(head, HELPER) == head / HELPER

    def test_a_missing_file_or_a_directory_is_absent(self, linked_trees: tuple[Path, Path]) -> None:
        _, head = linked_trees

        assert vdc._head_file(head, f"{DEMO_LINK}/scripts/nope.py") is None
        assert vdc._head_file(head, DEMO_LINK) is None

    def test_a_file_through_a_link_that_leaves_the_tree_is_absent(
        self, linked_trees: tuple[Path, Path]
    ) -> None:
        base, head = linked_trees
        _relink(head, _outside_copy(head, base))

        assert (head / HELPER).is_file()
        assert vdc._head_file(head, HELPER) is None


class TestFollowing:
    def test_restores_the_gate_table_even_when_the_body_raises(self) -> None:
        gate = vdc._load_gate(REPO_ROOT)
        before = gate._PINNED_LINKS

        with pytest.raises(RuntimeError), vdc._following(gate, REPO_ROOT, {"a": "b"}):
            assert gate._PINNED_LINKS == (REPO_ROOT, {"a": "b"})
            raise RuntimeError

        assert gate._PINNED_LINKS is before
