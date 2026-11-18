"""Mirror orphan prune fails closed on unreadable input and on every kind of link.

Review threads on PR #7432: an unreadable NO-REGEN marker, an unreadable source
subdirectory, a Windows junction, and a relative target path each used to let
the prune delete a file it should have kept. Each test here fails without its
fix.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import skill_mirror_prune  # noqa: E402
from _skill_mirror_helpers import build as _build  # noqa: E402
from _skill_mirror_helpers import built_repo as _built_repo  # noqa: E402
from _skill_mirror_helpers import make_symlink  # noqa: E402
from _skill_mirror_helpers import mirror as _mirror  # noqa: E402
from _skill_mirror_helpers import seed as _seed  # noqa: E402
from skill_support_mirror import SkillSupportSyncError  # noqa: E402

_NEEDS_POSIX_PERMS = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 denies reads only to a non-root POSIX user",
)


@contextmanager
def _denied(path: Path) -> Iterator[None]:
    """Deny all access to ``path``; restore it so pytest can clean up."""
    mode = path.stat().st_mode & 0o777
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("filesystem ignores chmod 000")
        yield
    finally:
        path.chmod(mode)


def _flag_as_junctions(monkeypatch: pytest.MonkeyPatch, *paths: Path) -> None:
    """Make ``is_redirecting`` report the real entries at ``paths`` as junctions.

    A junction is a directory carrying a reparse tag, which Linux cannot create.
    The prune must decide through ``atomic_write.is_redirecting``, so the test
    forces that decision for chosen inodes and leaves everything else real.
    """
    inodes = {path.lstat().st_ino for path in paths}
    real = skill_mirror_prune.is_redirecting
    monkeypatch.setattr(
        skill_mirror_prune,
        "is_redirecting",
        lambda metadata: real(metadata) or metadata.st_ino in inodes,
    )


# --- unreadable NO-REGEN marker (fail closed) -------------------------------


@_NEEDS_POSIX_PERMS
def test_an_unreadable_orphan_is_never_deleted_and_blocks_the_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    mirror = _mirror(tmp_path)
    protected = mirror / "references" / "hand.md"
    protected.write_text("<!-- NO-REGEN: hand edited -->\nbody\n", encoding="utf-8")

    with _denied(protected):
        assert _build(tmp_path) == 1

    assert protected.read_text(encoding="utf-8").startswith("<!-- NO-REGEN")
    assert (mirror / "references" / "old.md").is_file(), "nothing is deleted for that skill"
    assert str(protected) in capsys.readouterr().err


@_NEEDS_POSIX_PERMS
def test_an_unreadable_orphan_raises_naming_the_path(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    protected = _mirror(tmp_path) / "references" / "hand.md"
    protected.write_text("x\n", encoding="utf-8")

    with _denied(protected), pytest.raises(SkillSupportSyncError, match="hand.md"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))


# --- unreadable source subdirectory (fail closed) ---------------------------


@_NEEDS_POSIX_PERMS
def test_an_unreadable_source_subdirectory_blocks_the_prune(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    mirror = _mirror(tmp_path)

    with _denied(source / "references"), pytest.raises(SkillSupportSyncError, match="references"):
        skill_mirror_prune.prune_mirror_orphans(source, mirror)

    assert (mirror / "references" / "keep.md").is_file()
    assert (mirror / "references" / "old.md").is_file()


@_NEEDS_POSIX_PERMS
def test_an_unreadable_source_subdirectory_fails_the_build_and_check(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)

    with _denied(source / "references"):
        assert _build(tmp_path) == 1
        assert _build(tmp_path, check=True) == 1

    assert (_mirror(tmp_path) / "references" / "keep.md").is_file()


# --- a file named exactly .noregen ------------------------------------------


def test_a_file_named_exactly_noregen_is_an_orphan_not_a_crash(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    bare = _mirror(tmp_path) / "references" / ".noregen"
    bare.write_text("", encoding="utf-8")

    assert skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path)) == 1
    assert not bare.exists()


def test_is_kept_sidecar_rejects_the_bare_suffix_and_keeps_a_real_sidecar(
    tmp_path: Path,
) -> None:
    (tmp_path / "pinned.md").write_text("x\n", encoding="utf-8")
    real = tmp_path / "pinned.md.noregen"
    real.write_text("", encoding="utf-8")
    bare = tmp_path / ".noregen"
    bare.write_text("", encoding="utf-8")

    assert skill_mirror_prune._is_kept_sidecar(real) is True
    assert skill_mirror_prune._is_kept_sidecar(bare) is False


# --- Windows junctions (decision tested through is_redirecting) -------------


def test_a_junction_at_an_unowned_directory_is_refused_and_not_descended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    junction = _mirror(tmp_path) / "elsewhere"
    junction.mkdir()
    stray = junction / "stray.md"
    stray.write_text("outside the mirror\n", encoding="utf-8")
    _flag_as_junctions(monkeypatch, junction)

    with pytest.raises(SkillSupportSyncError, match="elsewhere"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))

    assert stray.is_file()
    assert (_mirror(tmp_path) / "references" / "old.md").is_file()


def test_a_junction_at_an_owned_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _built_repo(tmp_path)
    _flag_as_junctions(monkeypatch, _mirror(tmp_path) / "references")

    with pytest.raises(SkillSupportSyncError, match="references.*CWE-59"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))


def test_a_redirecting_file_with_no_source_counterpart_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _built_repo(tmp_path)
    redirect = _mirror(tmp_path) / "references" / "redirect.md"
    redirect.write_text("x\n", encoding="utf-8")
    _flag_as_junctions(monkeypatch, redirect)

    with pytest.raises(SkillSupportSyncError, match="redirect.md"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))

    assert redirect.is_file()


def test_a_junctioned_target_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _built_repo(tmp_path)
    _flag_as_junctions(monkeypatch, _mirror(tmp_path))

    with pytest.raises(SkillSupportSyncError, match="mirror skill directory"):
        skill_mirror_prune.prune_mirror_orphans(source, _mirror(tmp_path))

    assert (_mirror(tmp_path) / "references" / "old.md").is_file()


def test_a_file_that_turns_into_a_junction_before_removal_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "mirror"
    target.mkdir()
    late = target / "late.md"
    late.write_text("x\n", encoding="utf-8")
    _flag_as_junctions(monkeypatch, late)

    with pytest.raises(SkillSupportSyncError, match="became a symlink"):
        skill_mirror_prune._remove_orphan(late, target)

    assert late.is_file()


def _git_repo_with_linked_skills(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return ``(repo, source, orphan)`` with ``out/skills`` standing in for a link."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = _seed(repo)
    real = repo / "real"
    (real / "alpha").mkdir(parents=True)
    orphan = real / "alpha" / "stray.md"
    orphan.write_text("stray\n", encoding="utf-8")
    (repo / "out").mkdir()
    return repo, source, orphan


def test_a_junctioned_ancestor_inside_a_git_repo_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source, orphan = _git_repo_with_linked_skills(tmp_path)
    (repo / "out" / "skills").mkdir()
    (repo / "out" / "skills" / "alpha").mkdir()
    (repo / "out" / "skills" / "alpha" / "stray.md").write_text("s\n", encoding="utf-8")
    _flag_as_junctions(monkeypatch, repo / "out" / "skills")

    with pytest.raises(SkillSupportSyncError, match="symlinked ancestor"):
        skill_mirror_prune.prune_mirror_orphans(source, repo / "out" / "skills" / "alpha")

    assert (repo / "out" / "skills" / "alpha" / "stray.md").is_file()
    assert orphan.is_file()


# --- relative target path ---------------------------------------------------


def test_a_relative_target_under_a_symlinked_ancestor_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source, orphan = _git_repo_with_linked_skills(tmp_path)
    make_symlink(repo / "out" / "skills", repo / "real", directory=True)
    monkeypatch.chdir(repo)

    with pytest.raises(SkillSupportSyncError, match="symlinked ancestor"):
        skill_mirror_prune.prune_mirror_orphans(source, Path("out/skills/alpha"))

    assert orphan.is_file()
