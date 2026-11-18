"""A mirror skill file with no source counterpart is pruned, or reported as drift.

``skill_support_mirror._copy_skill_tree`` walks source files forward only. A
support file deleted or renamed in ``src/claude/skills/<name>/`` left its old
copy in every mirror tree (copilot-cli, codex, cursor, muse), and
``build_all.py --check`` passed, so stale reference text shipped. These tests
cover :func:`skill_support_mirror.prune_mirror_orphans` and its wiring in
``generate_skills``: removal, ownership, ``--check`` (exit 2 through
``build_all``), and the refusal to delete a symlink or anything outside the
owned mirror skill directory.
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

import build_all  # noqa: E402
import generate_skills  # noqa: E402
import skill_mirror_prune  # noqa: E402
import skill_support_mirror  # noqa: E402
from _skill_mirror_helpers import SHAPES, make_symlink  # noqa: E402
from _skill_mirror_helpers import build as _build  # noqa: E402
from _skill_mirror_helpers import built_repo as _built_repo  # noqa: E402
from _skill_mirror_helpers import config as _config  # noqa: E402
from _skill_mirror_helpers import mirror as _mirror  # noqa: E402
from _skill_mirror_helpers import seed as _seed  # noqa: E402
from skill_copy_compare import mirror_owned_rels  # noqa: E402

_NEEDS_SYMLINKS = pytest.mark.skipif(
    sys.platform == "win32", reason="creating symlinks needs elevated rights on Windows"
)
_ALL_SHAPES = pytest.mark.parametrize("shape", sorted(SHAPES))


# --- removal ---------------------------------------------------------------


@_ALL_SHAPES
def test_removed_source_file_is_pruned_from_the_mirror(tmp_path: Path, shape: str) -> None:
    source = _built_repo(tmp_path, shape)
    (source / "references" / "old.md").unlink()

    assert _build(tmp_path, shape) == 0

    mirror = _mirror(tmp_path)
    assert not (mirror / "references" / "old.md").exists()
    assert (mirror / "references" / "keep.md").read_text(encoding="utf-8") == "keep\n"
    assert (mirror / "scripts" / "run.py").is_file()
    assert (mirror / "SKILL.md").is_file()


@_ALL_SHAPES
def test_renamed_source_file_leaves_no_old_copy(tmp_path: Path, shape: str) -> None:
    source = _built_repo(tmp_path, shape)
    (source / "references" / "old.md").rename(source / "references" / "new.md")

    assert _build(tmp_path, shape) == 0

    mirror = _mirror(tmp_path)
    assert not (mirror / "references" / "old.md").exists()
    assert (mirror / "references" / "new.md").read_text(encoding="utf-8") == "old\n"


def test_a_directory_emptied_by_the_prune_is_removed(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    (source / "scripts" / "run.py").unlink()
    (source / "scripts").rmdir()

    assert _build(tmp_path) == 0

    assert not (_mirror(tmp_path) / "scripts").exists()
    assert (_mirror(tmp_path) / "references").is_dir()


def test_a_directory_the_prune_did_not_empty_stays(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    preexisting_empty = _mirror(tmp_path) / "unrelated-empty"
    preexisting_empty.mkdir()

    assert _build(tmp_path) == 0

    assert (_mirror(tmp_path) / "references").is_dir()
    assert preexisting_empty.is_dir()


def test_a_clean_second_run_prunes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _built_repo(tmp_path)
    capsys.readouterr()

    assert _build(tmp_path) == 0

    assert "Orphan mirror files removed: 0" in capsys.readouterr().out


def test_what_if_reports_the_orphan_and_keeps_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    orphan = _mirror(tmp_path) / "references" / "old.md"

    rc = generate_skills.generate_skills(_config(tmp_path), tmp_path, what_if=True)

    assert rc == 0
    assert orphan.is_file()
    assert f"Would remove: {orphan}" in capsys.readouterr().out


# --- ownership: what the generator adds stays ------------------------------


def test_generator_owned_mirror_files_are_kept(tmp_path: Path) -> None:
    """SKILL.md, a lib-rendered sidecar, bytecode, and NO-REGEN files are never orphans."""
    source = _built_repo(tmp_path, name="review")
    (source / "references" / "old.md").unlink()
    mirror = _mirror(tmp_path, "review")
    sidecar = mirror / "scripts" / "validate_review_marker.py"
    sidecar.write_text("rendered from scripts/validation\n", encoding="utf-8")
    pyc = mirror / "scripts" / "__pycache__" / "run.cpython-314.pyc"
    pyc.parent.mkdir()
    pyc.write_bytes(b"\x00")
    protected = mirror / "references" / "hand.md"
    protected.write_text("<!-- NO-REGEN: hand edited -->\nbody\n", encoding="utf-8")
    sidecar_owner = mirror / "references" / "pinned.md"
    sidecar_owner.write_text("pinned\n", encoding="utf-8")
    sidecar_marker = mirror / "references" / "pinned.md.noregen"
    sidecar_marker.write_text("", encoding="utf-8")

    assert _build(tmp_path) == 0

    assert not (mirror / "references" / "old.md").exists()
    for kept in (mirror / "SKILL.md", sidecar, pyc, protected, sidecar_owner, sidecar_marker):
        assert kept.exists(), kept


def test_owned_set_is_the_copy_enumeration_plus_skill_md_and_skips(tmp_path: Path) -> None:
    source = _seed(tmp_path)
    (source / "scripts" / "__pycache__").mkdir()
    (source / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    extra = frozenset({Path("scripts/rendered.py")})

    owned = mirror_owned_rels(source, extra)

    assert owned == {
        Path("SKILL.md"),
        Path("references/keep.md"),
        Path("references/old.md"),
        Path("scripts/run.py"),
        Path("scripts/rendered.py"),
    }


def test_a_skill_with_no_mirror_directory_is_a_noop(tmp_path: Path) -> None:
    source = _seed(tmp_path)

    assert skill_support_mirror.prune_mirror_orphans(source, tmp_path / "absent") == 0


# --- --check ----------------------------------------------------------------


@_ALL_SHAPES
def test_check_reports_an_orphan_and_leaves_it_in_place(
    tmp_path: Path, shape: str, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _built_repo(tmp_path, shape)
    (source / "references" / "old.md").unlink()
    orphan = _mirror(tmp_path) / "references" / "old.md"
    capsys.readouterr()

    assert _build(tmp_path, shape, check=True) == 1

    assert orphan.is_file()
    assert f"DRIFT: {orphan}" in capsys.readouterr().out


def test_build_all_check_exits_2_on_an_orphan_without_deleting_it(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    orphan = _mirror(tmp_path) / "references" / "old.md"

    result = build_all._build_skills(tmp_path, _config(tmp_path), "copilot-cli", check=True)

    assert result.exit_code == 2
    assert orphan.is_file()


def test_build_all_check_passes_on_a_clean_mirror(tmp_path: Path) -> None:
    _built_repo(tmp_path)

    result = build_all._build_skills(tmp_path, _config(tmp_path), "copilot-cli", check=True)

    assert result.exit_code == 0


def test_check_wins_over_what_if(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()

    count = skill_support_mirror.prune_mirror_orphans(
        source, _mirror(tmp_path), what_if=True, check=True
    )

    assert count == 1
    assert "DRIFT:" in capsys.readouterr().out


# --- negative control -------------------------------------------------------


def test_negative_control_forward_only_copy_keeps_the_orphan_and_passes_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the prune disabled (the old forward-only copy) the defect reproduces.

    The orphan survives a write run, and ``--check`` passes over it. The tests
    above fail in exactly this configuration, so they do detect the defect.
    """
    monkeypatch.setattr(generate_skills, "prune_mirror_orphans", lambda *a, **kw: 0)
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()

    assert _build(tmp_path) == 0
    assert (_mirror(tmp_path) / "references" / "old.md").is_file()
    assert _build(tmp_path, check=True) == 0


# --- safety: never delete a link or anything outside the mirror skill ------


def _external(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("precious\n", encoding="utf-8")
    return outside


@_NEEDS_SYMLINKS
def test_a_symlinked_file_with_no_source_counterpart_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    outside = _external(tmp_path)
    link = _mirror(tmp_path) / "references" / "link.md"
    make_symlink(link, outside / "precious.txt")

    assert _build(tmp_path) == 1

    assert link.is_symlink()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "precious\n"
    assert (_mirror(tmp_path) / "references" / "old.md").is_file(), "nothing is deleted on refusal"
    assert "symlink with no source counterpart refused" in capsys.readouterr().err


@_NEEDS_SYMLINKS
def test_a_symlinked_directory_is_neither_followed_nor_deleted(tmp_path: Path) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    outside = _external(tmp_path)
    link = _mirror(tmp_path) / "linked"
    make_symlink(link, outside, directory=True)

    assert _build(tmp_path) == 1

    assert link.is_symlink()
    assert (outside / "precious.txt").is_file()


@_NEEDS_SYMLINKS
def test_a_symlinked_mirror_skill_directory_is_refused(tmp_path: Path) -> None:
    source = _seed(tmp_path)
    outside = _external(tmp_path)
    (outside / "stray.md").write_text("stray\n", encoding="utf-8")
    (tmp_path / "out" / "skills").mkdir(parents=True)
    make_symlink(_mirror(tmp_path), outside, directory=True)

    with pytest.raises(skill_support_mirror.SkillSupportSyncError, match="symlinked mirror"):
        skill_support_mirror.prune_mirror_orphans(source, _mirror(tmp_path))

    assert (outside / "stray.md").is_file()
    assert (outside / "precious.txt").is_file()


@_NEEDS_SYMLINKS
def test_a_symlink_at_an_owned_path_is_left_for_the_copy(tmp_path: Path) -> None:
    source = _seed(tmp_path)
    outside = _external(tmp_path)
    mirror = _mirror(tmp_path)
    (mirror / "references").mkdir(parents=True)
    make_symlink((mirror / "references" / "keep.md"), outside / "precious.txt")

    assert skill_support_mirror.prune_mirror_orphans(source, mirror) == 0
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "precious\n"


@_NEEDS_SYMLINKS
def test_a_symlink_swapped_in_before_removal_is_refused(tmp_path: Path) -> None:
    outside = _external(tmp_path)
    target = tmp_path / "mirror"
    target.mkdir()
    link = target / "late.md"
    make_symlink(link, outside / "precious.txt")

    with pytest.raises(skill_support_mirror.SkillSupportSyncError, match="became a symlink"):
        skill_mirror_prune._remove_orphan(link, target)

    assert (outside / "precious.txt").is_file()


def test_an_unlink_failure_raises_and_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()

    def _deny(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "unlink", _deny)

    with pytest.raises(skill_support_mirror.SkillSupportSyncError, match="old.md.*denied"):
        skill_support_mirror.prune_mirror_orphans(source, _mirror(tmp_path))


def test_only_the_mirror_skill_directory_is_touched(tmp_path: Path) -> None:
    """A sibling skill's files and files beside the mirror skill are never removed."""
    source = _built_repo(tmp_path)
    (source / "references" / "old.md").unlink()
    sibling = tmp_path / "out" / "skills" / "other" / "references" / "stray.md"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("stray\n", encoding="utf-8")
    beside = tmp_path / "out" / "skills" / "README.txt"
    beside.write_text("hand\n", encoding="utf-8")

    assert _build(tmp_path) == 0

    assert sibling.is_file()
    assert beside.is_file()
