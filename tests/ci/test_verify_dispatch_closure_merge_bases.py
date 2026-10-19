"""Every merge base counts for STALE in verify_dispatch_closure.py (issue #6506).

After a criss-cross merge a head and the base ref share several best common
ancestors. Plain ``git merge-base`` prints one of them, and the head's author
shapes the history that picks it. A path is STALE only when the head matches it
at every merge base.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import git, rev, write


def _commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        message,
    )
    return rev(root)


@pytest.fixture
def criss_cross(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    """A repository whose base tip and head share two best common ancestors.

    Returns ``(root, base_tip, head, first_fork, second_fork)``. The file ``f``
    holds ``one`` at the first fork, ``two`` at the second, and ``three`` at both
    tips, so no single value is shared by every merge base.
    """
    root = tmp_path / "criss"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, "f", "zero\n")
    root_commit = _commit(root, "root")
    git(root, "checkout", "-q", "-b", "left", root_commit)
    write(root, "f", "one\n")
    first = _commit(root, "left")
    git(root, "checkout", "-q", "-b", "right", root_commit)
    write(root, "f", "two\n")
    second = _commit(root, "right")
    git(root, "checkout", "-q", "-b", "tip", first)
    git(
        root,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "merge",
        "-q",
        "-s",
        "ours",
        "--no-edit",
        second,
    )
    write(root, "f", "three\n")
    write(root, "late", "new on the base tip\n")
    base_tip = _commit(root, "base tip")
    git(root, "checkout", "-q", "right")
    git(
        root,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "merge",
        "-q",
        "-s",
        "ours",
        "--no-edit",
        first,
    )
    write(root, "f", "head\n")
    head = _commit(root, "head")
    return root, base_tip, head, first, second


class TestCrissCrossMergeBases:
    def test_all_best_common_ancestors_are_returned(
        self, criss_cross: tuple[Path, str, str, str, str]
    ) -> None:
        root, base_tip, head, first, second = criss_cross

        assert sorted(vdc._merge_bases(root, base_tip, head)) == sorted([first, second])

    def test_a_head_matching_only_one_merge_base_is_changed_not_stale(
        self, criss_cross: tuple[Path, str, str, str, str]
    ) -> None:
        """Plain merge-base picks one ancestor; the head shapes which one."""
        root, base_tip, head, first, second = criss_cross
        git(root, "checkout", "-q", head)
        write(root, "f", "one\n")
        matches_first_only = _commit(root, "head equals the first fork")

        kind = vdc._classify(root, base_tip, root, matches_first_only, "f", [first, second])

        assert kind == vdc.CHANGED

    def test_a_head_matching_every_merge_base_is_stale(
        self, criss_cross: tuple[Path, str, str, str, str]
    ) -> None:
        root, base_tip, _head, first, _second = criss_cross
        git(root, "checkout", "-q", first)
        write(root, "g", "unrelated\n")
        first_twin = _commit(root, "same f as the first fork")

        kind = vdc._classify(root, base_tip, root, first_twin, "f", [first, first_twin])

        assert kind == vdc.STALE

    def test_no_merge_bases_means_changed(
        self, criss_cross: tuple[Path, str, str, str, str]
    ) -> None:
        root, base_tip, head, _first, _second = criss_cross

        assert vdc._classify(root, base_tip, root, head, "f", []) == vdc.CHANGED
        assert vdc._classify(root, base_tip, root, head, "f", None) == vdc.CHANGED

    def test_a_missing_root_is_stale_only_when_every_merge_base_lacks_it(
        self, criss_cross: tuple[Path, str, str, str, str], tmp_path: Path
    ) -> None:
        root, base_tip, _head, first, second = criss_cross
        empty = tmp_path / "empty-head"
        empty.mkdir()

        # "late" is new on the base tip: neither fork has it, so a head without it is stale.
        assert vdc._missing_roots(root, empty, base_tip, ["late"], [first, second]) == (
            [],
            ["late"],
        )
        # One "fork" that has it (the tip itself) means the head deleted it.
        assert vdc._missing_roots(root, empty, base_tip, ["late"], [first, base_tip]) == (
            ["late"],
            [],
        )
        assert vdc._missing_roots(root, empty, base_tip, ["late"], []) == (["late"], [])
