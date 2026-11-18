"""Mirror orphan prune: symlinks at owned directories, ancestors, case, no repo.

Review round 1 on the prune. The basic removal, ownership and ``--check``
cases live in ``test_skill_mirror_orphans.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import generate_skills  # noqa: E402
import skill_mirror_prune  # noqa: E402
import skill_support_mirror  # noqa: E402
from _skill_mirror_helpers import build as _build  # noqa: E402
from _skill_mirror_helpers import built_repo as _built_repo  # noqa: E402
from _skill_mirror_helpers import make_symlink  # noqa: E402
from _skill_mirror_helpers import mirror as _mirror  # noqa: E402
from _skill_mirror_helpers import seed as _seed  # noqa: E402

_NEEDS_SYMLINKS = pytest.mark.skipif(
    sys.platform == "win32", reason="creating symlinks needs elevated rights on Windows"
)


def _link_references_outside(tmp_path: Path) -> Path:
    """Move the mirror's ``references`` outside, link it back, tamper keep.md."""
    outside = tmp_path / "outside"
    mirror = _mirror(tmp_path)
    (mirror / "references").rename(outside)
    make_symlink(mirror / "references", outside, directory=True)
    (outside / "keep.md").write_text("tampered\n", encoding="utf-8")
    return outside


@_NEEDS_SYMLINKS
def test_a_symlink_at_an_owned_directory_path_fails_in_write_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _built_repo(tmp_path)
    outside = _link_references_outside(tmp_path)

    assert _build(tmp_path) == 1

    assert (outside / "keep.md").read_text(encoding="utf-8") == "tampered\n", "no write-through"
    assert (_mirror(tmp_path) / "references").is_symlink()
    assert "symlink at an owned directory path refused" in capsys.readouterr().err


@_NEEDS_SYMLINKS
def test_a_symlink_at_an_owned_directory_path_fails_in_check_mode(tmp_path: Path) -> None:
    _built_repo(tmp_path)
    outside = _link_references_outside(tmp_path)
    (outside / "keep.md").write_text("keep\n", encoding="utf-8")  # matches the source

    assert _build(tmp_path, check=True) == 1

    assert (_mirror(tmp_path) / "references").is_symlink()


@_NEEDS_SYMLINKS
def test_owned_directory_link_error_names_the_path(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    _link_references_outside(tmp_path)

    with pytest.raises(skill_support_mirror.SkillSupportSyncError, match="references.*CWE-59"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))


@_NEEDS_SYMLINKS
def test_negative_control_without_the_guard_the_copy_writes_through_the_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the guard disabled the copy overwrites a file outside the mirror and check passes."""
    _built_repo(tmp_path)
    outside = _link_references_outside(tmp_path)
    monkeypatch.setattr(generate_skills, "prune_mirror_orphans", lambda *a, **kw: 0)

    assert _build(tmp_path) == 0
    assert (outside / "keep.md").read_text(encoding="utf-8") == "keep\n"
    (outside / "keep.md").write_text("keep\n", encoding="utf-8")
    assert _build(tmp_path, check=True) == 0


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


@_NEEDS_SYMLINKS
def test_a_symlinked_ancestor_inside_a_git_repo_is_refused(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    source = _seed(repo)
    real = repo / "real"
    (real / "alpha").mkdir(parents=True)
    orphan = real / "alpha" / "stray.md"
    orphan.write_text("stray\n", encoding="utf-8")
    (repo / "out").mkdir()
    make_symlink((repo / "out" / "skills"), real, directory=True)

    with pytest.raises(skill_support_mirror.SkillSupportSyncError, match="symlinked ancestor"):
        skill_mirror_prune.prune_mirror_orphans(source, repo / "out" / "skills" / "alpha")

    assert orphan.is_file()


@_NEEDS_SYMLINKS
def test_outside_a_repo_only_the_target_is_checked_and_the_prune_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documented choice: with no repository root, ancestors are not confined.

    The prune still never follows a link and unlinks only regular files, so it
    removes the orphan under the linked parent and nothing else.
    """
    monkeypatch.setattr(skill_mirror_prune, "find_repo_root", lambda _path: None)
    source = _seed(tmp_path)
    real = tmp_path / "real"
    (real / "alpha").mkdir(parents=True)
    orphan = real / "alpha" / "stray.md"
    orphan.write_text("stray\n", encoding="utf-8")
    (tmp_path / "out").mkdir()
    make_symlink((tmp_path / "out" / "skills"), real, directory=True)

    assert skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path)) == 1
    assert not orphan.exists()


def test_a_case_only_difference_from_an_owned_path_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """On APFS ``Foo.md`` and ``foo.md`` are one file; deleting it removes the only copy."""
    source = _seed(tmp_path)
    (source / "references" / "foo.md").write_text("foo\n", encoding="utf-8")
    mirror = _mirror(tmp_path)
    (mirror / "references").mkdir(parents=True)
    variant = mirror / "references" / "Foo.md"
    variant.write_text("foo\n", encoding="utf-8")

    assert skill_mirror_prune.prune_mirror_orphans(source, mirror) == 0

    assert variant.is_file()
    assert "differs from a source path only by case" in capsys.readouterr().out


def test_a_name_that_differs_by_more_than_case_is_still_pruned(tmp_path: Path) -> None:
    source = _seed(tmp_path)
    mirror = _mirror(tmp_path)
    (mirror / "references").mkdir(parents=True)
    other = mirror / "references" / "Keep2.md"
    other.write_text("x\n", encoding="utf-8")

    assert skill_mirror_prune.prune_mirror_orphans(source, mirror) == 1
    assert not other.exists()
