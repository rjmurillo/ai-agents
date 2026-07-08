"""Tests for packed-refs repair."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from scripts.maintenance import repair_packed_refs as repair_module
from scripts.maintenance.repair_packed_refs import repair_packed_refs

PACKED_REFS_HEADER = b"# pack-refs with: peeled fully-peeled sorted\n"
REF_LINE = b"72015a50526a72200973a9a3e817195727f15f96 refs/remotes/origin/main\n"
PEELED_LINE = b"^1111111111111111111111111111111111111111\n"


def test_repairs_corrupted_packed_refs_and_preserves_refs(tmp_path: Path) -> None:
    """Blank lines are removed and real ref records remain unchanged."""
    worktree = _create_normal_worktree(tmp_path)
    packed_refs = worktree / ".git" / "packed-refs"
    original = PACKED_REFS_HEADER + b"\n" + REF_LINE + PEELED_LINE + b"\n"
    packed_refs.write_bytes(original)
    verified_roots: list[Path] = []

    result = repair_packed_refs(worktree, verifier=verified_roots.append)

    assert result.status == "repaired"
    assert result.removed_blank_lines == 2
    assert packed_refs.read_bytes() == PACKED_REFS_HEADER + REF_LINE + PEELED_LINE
    assert result.backup_path is not None
    assert result.backup_path.read_bytes() == original
    assert verified_roots == [worktree]


def test_leaves_clean_packed_refs_byte_identical(tmp_path: Path) -> None:
    """Clean packed-refs content is not rewritten or backed up."""
    worktree = _create_normal_worktree(tmp_path)
    packed_refs = worktree / ".git" / "packed-refs"
    original = PACKED_REFS_HEADER + REF_LINE
    packed_refs.write_bytes(original)
    verifier_called = False

    def verifier(_worktree: Path) -> None:
        nonlocal verifier_called
        verifier_called = True

    result = repair_packed_refs(worktree, verifier=verifier)

    assert result.status == "clean"
    assert packed_refs.read_bytes() == original
    assert not (worktree / ".git" / "packed-refs.before-repair").exists()
    assert verifier_called is False


def test_missing_packed_refs_is_clean_noop(tmp_path: Path) -> None:
    """A repository without packed-refs exits without creating a file."""
    worktree = _create_normal_worktree(tmp_path)
    verifier_called = False

    def verifier(_worktree: Path) -> None:
        nonlocal verifier_called
        verifier_called = True

    result = repair_packed_refs(worktree, verifier=verifier)

    assert result.status == "missing"
    assert result.packed_refs_path == worktree / ".git" / "packed-refs"
    assert not result.packed_refs_path.exists()
    assert verifier_called is False


def test_resolves_linked_worktree_common_git_dir(tmp_path: Path) -> None:
    """Linked worktrees repair packed-refs in the common git directory."""
    common_git = tmp_path / "repo" / ".git"
    linked_git = common_git / "worktrees" / "feature"
    linked_worktree = tmp_path / "feature"
    linked_git.mkdir(parents=True)
    linked_worktree.mkdir()
    (linked_git / "commondir").write_text("../..", encoding="utf-8")
    (linked_worktree / ".git").write_text(f"gitdir: {linked_git}\n", encoding="utf-8")
    packed_refs = common_git / "packed-refs"
    packed_refs.write_bytes(PACKED_REFS_HEADER + b"\n" + REF_LINE)

    result = repair_packed_refs(linked_worktree, verifier=lambda _worktree: None)

    assert result.status == "repaired"
    assert result.packed_refs_path == packed_refs
    assert packed_refs.read_bytes() == PACKED_REFS_HEADER + REF_LINE


def test_header_only_packed_refs_is_clean_noop(tmp_path: Path) -> None:
    """A packed-refs file with a header and no refs is valid."""
    worktree = _create_normal_worktree(tmp_path)
    packed_refs = worktree / ".git" / "packed-refs"
    packed_refs.write_bytes(PACKED_REFS_HEADER)

    result = repair_packed_refs(worktree, verifier=lambda _worktree: None)

    assert result.status == "clean"
    assert packed_refs.read_bytes() == PACKED_REFS_HEADER
    assert not (worktree / ".git" / "packed-refs.before-repair").exists()


def test_restores_backup_when_verification_fails(tmp_path: Path) -> None:
    """A failed git verification restores the original packed-refs bytes."""
    worktree = _create_normal_worktree(tmp_path)
    packed_refs = worktree / ".git" / "packed-refs"
    original = PACKED_REFS_HEADER + b"\n" + REF_LINE
    packed_refs.write_bytes(original)

    def fail_verifier(_worktree: Path) -> None:
        raise RuntimeError("git rejected refs")

    with pytest.raises(RuntimeError, match="git rejected refs"):
        repair_packed_refs(worktree, verifier=fail_verifier)

    assert packed_refs.read_bytes() == original
    assert (worktree / ".git" / "packed-refs.before-repair").read_bytes() == original


def test_repair_preserves_packed_refs_permissions(tmp_path: Path) -> None:
    """Repair keeps the original packed-refs file mode."""
    worktree = _create_normal_worktree(tmp_path)
    packed_refs = worktree / ".git" / "packed-refs"
    original_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
    packed_refs.write_bytes(PACKED_REFS_HEADER + b"\n" + REF_LINE)
    packed_refs.chmod(original_mode)

    result = repair_packed_refs(worktree, verifier=lambda _worktree: None)

    assert result.status == "repaired"
    assert stat.S_IMODE(packed_refs.stat().st_mode) == original_mode


def test_write_failure_unlinks_temp_after_file_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed temp writes clean up after the context manager closes the file."""
    packed_refs = tmp_path / "packed-refs"
    packed_refs.write_bytes(PACKED_REFS_HEADER)
    temp_closed = False

    class FailingTempFile:
        def __init__(self, directory: Path) -> None:
            self.path = directory / "repair.tmp"
            self.name = str(self.path)
            self.handle = self.path.open("wb")

        def __enter__(self) -> FailingTempFile:
            return self

        def __exit__(self, *_args: object) -> None:
            nonlocal temp_closed
            self.handle.close()
            temp_closed = True

        def write(self, _data: bytes) -> int:
            raise OSError("write failed")

        def flush(self) -> None:
            self.handle.flush()

        def fileno(self) -> int:
            return self.handle.fileno()

    def fake_named_temporary_file(*, dir: Path, delete: bool) -> FailingTempFile:
        assert delete is False
        return FailingTempFile(Path(dir))

    original_unlink = Path.unlink

    def assert_closed_before_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name == "repair.tmp":
            assert temp_closed is True
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(
        repair_module.tempfile, "NamedTemporaryFile", fake_named_temporary_file
    )
    monkeypatch.setattr(Path, "unlink", assert_closed_before_unlink)

    with pytest.raises(OSError, match="write failed"):
        repair_module._write_repaired_packed_refs(packed_refs, REF_LINE)

    assert not (tmp_path / "repair.tmp").exists()
    assert packed_refs.read_bytes() == PACKED_REFS_HEADER


def _create_normal_worktree(parent: Path) -> Path:
    worktree = parent / "repo"
    git_dir = worktree / ".git"
    git_dir.mkdir(parents=True)
    return worktree
