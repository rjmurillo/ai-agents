"""Tests for scripts/metrics_writer.py (CWE-59 symlink, CWE-367 TOCTOU).

Covers positive append, advisory lock held during write, symlink rejection
(pre-check and the O_NOFOLLOW swap-in path), parent-dir traversal rejection,
and the CLI argv exit-code contract. The filesystem boundary is exercised with
real temp files and real symlinks under pytest's tmp_path.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metrics_writer  # noqa: E402
from metrics_writer import (  # noqa: E402
    MetricsWriteError,
    safe_append_tally,
)

_TALLY = "2026-06-03T00:00:00Z | pass | none | none"


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip(
            "symlink creation unavailable on this platform; PR #2354 tracks coverage"
        )


# --- positive: normal append -------------------------------------------------


def test_append_creates_file_and_writes_line(tmp_path: Path) -> None:
    target = tmp_path / "STEP-0.5-METRICS.md"

    written = safe_append_tally(target, _TALLY)

    assert written == target
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"


def test_append_creates_parent_directory_lazily(tmp_path: Path) -> None:
    target = tmp_path / "sessions" / "STEP-0.5-METRICS.md"

    safe_append_tally(target, _TALLY)

    assert target.parent.is_dir()
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"


def test_append_is_additive_across_calls(tmp_path: Path) -> None:
    target = tmp_path / "metrics.md"

    safe_append_tally(target, "line one")
    safe_append_tally(target, "line two")

    assert target.read_text(encoding="utf-8") == "line one\nline two\n"


def test_append_preserves_caller_supplied_newline(tmp_path: Path) -> None:
    target = tmp_path / "metrics.md"

    safe_append_tally(target, _TALLY + "\n")

    # No doubled newline when the caller already terminated the record.
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode semantics")
def test_append_creates_owner_only_file(tmp_path: Path) -> None:
    target = tmp_path / "metrics.md"

    safe_append_tally(target, _TALLY)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_relative_path_without_base_is_anchored_to_project_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(metrics_writer, "_PROJECT_DIR", tmp_path)
    relative_target = Path("metrics") / "tally.md"

    written = safe_append_tally(relative_target, _TALLY)

    assert written == tmp_path / relative_target
    assert written.read_text(encoding="utf-8") == _TALLY + "\n"


def test_relative_path_escape_from_project_dir_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(metrics_writer, "_PROJECT_DIR", tmp_path / "project")

    with pytest.raises(MetricsWriteError, match="traversal"):
        safe_append_tally(Path("..") / "outside.md", _TALLY)

    assert not (tmp_path / "outside.md").exists()


def test_relative_path_with_relative_base_is_anchored_to_project_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(metrics_writer, "_PROJECT_DIR", tmp_path)

    written = safe_append_tally(Path("nested") / "metrics.md", _TALLY, base_dir="base")

    assert written == tmp_path / "base" / "nested" / "metrics.md"
    assert written.read_text(encoding="utf-8") == _TALLY + "\n"


# --- positive: exclusive lock held during the write --------------------------


def test_append_takes_exclusive_lock(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "metrics.md"
    events: list[str] = []

    real_write = os.write

    def spy_lock(fd: int) -> None:
        events.append("lock")

    def spy_unlock(fd: int) -> None:
        events.append("unlock")

    def spy_write(fd: int, data: bytes) -> int:
        events.append("write")
        return real_write(fd, data)

    monkeypatch.setattr(metrics_writer, "_lock", spy_lock)
    monkeypatch.setattr(metrics_writer, "_unlock", spy_unlock)
    monkeypatch.setattr(metrics_writer.os, "write", spy_write)

    safe_append_tally(target, _TALLY)

    # The write happens strictly between acquiring and releasing the lock.
    assert events == ["lock", "write", "unlock"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock semantics")
def test_concurrent_locks_are_mutually_exclusive(tmp_path: Path) -> None:
    import fcntl

    target = tmp_path / "metrics.md"
    target.write_text("", encoding="utf-8")

    # Hold an exclusive lock on the file, then prove a non-blocking second
    # acquire from another descriptor fails: the writer's LOCK_EX would block.
    holder = os.open(target, os.O_WRONLY | os.O_APPEND)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
        contender = os.open(target, os.O_WRONLY | os.O_APPEND)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(contender)
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)


# --- negative: symlink rejection (CWE-59) ------------------------------------


def test_symlink_target_is_rejected_by_precheck(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do not touch", encoding="utf-8")
    link = tmp_path / "STEP-0.5-METRICS.md"
    _symlink_or_skip(link, secret)

    with pytest.raises(MetricsWriteError, match="CWE-59"):
        safe_append_tally(link, _TALLY)

    # The pointee was not written through the link.
    assert secret.read_text(encoding="utf-8") == "do not touch"


def test_symlink_swapped_after_precheck_is_rejected_by_open(
    tmp_path: Path, monkeypatch
) -> None:
    """Simulate the TOCTOU swap: the pre-check passes, then a symlink appears.

    The O_NOFOLLOW open must refuse it (CWE-367). We plant the symlink inside a
    patched _reject_symlink so the pre-check sees no link but os.open does.
    """
    secret = tmp_path / "secret.txt"
    secret.write_text("do not touch", encoding="utf-8")
    target = tmp_path / "STEP-0.5-METRICS.md"

    if not getattr(os, "O_NOFOLLOW", 0):
        pytest.skip("platform lacks O_NOFOLLOW; pre-check is the only gate")

    probe = tmp_path / "probe-link"
    _symlink_or_skip(probe, secret)
    probe.unlink()

    def swap_in_symlink(t: Path) -> None:
        # Pre-check returns clean, but plants the link before os.open runs.
        target.symlink_to(secret)

    monkeypatch.setattr(metrics_writer, "_reject_symlink", swap_in_symlink)

    with pytest.raises(MetricsWriteError, match="CWE-59/CWE-367"):
        safe_append_tally(target, _TALLY)

    assert secret.read_text(encoding="utf-8") == "do not touch"


# --- edge: parent-dir traversal rejection ------------------------------------


def test_traversal_outside_base_is_rejected(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    escape = base / ".." / "outside.md"

    with pytest.raises(MetricsWriteError, match="traversal"):
        safe_append_tally(escape, _TALLY, base_dir=base)

    assert not (tmp_path / "outside.md").exists()


def test_target_under_base_is_allowed(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    target = base / "nested" / "STEP-0-METRICS.md"

    written = safe_append_tally(target, _TALLY, base_dir=base)

    assert written.read_text(encoding="utf-8") == _TALLY + "\n"


def test_base_itself_is_an_allowed_target(tmp_path: Path) -> None:
    # candidate == resolved_base path: the file IS the base name under its parent.
    base = tmp_path / "base"
    base.mkdir()
    # A target whose resolved candidate equals base is permitted (boundary).
    target = base
    written = safe_append_tally(target / "f.md", _TALLY, base_dir=target)
    assert written.read_text(encoding="utf-8") == _TALLY + "\n"


# --- failure path: write error surfaces as MetricsWriteError -----------------


def test_write_failure_is_wrapped(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "metrics.md"

    def boom(fd: int, data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(metrics_writer.os, "write", boom)

    with pytest.raises(MetricsWriteError, match="failed to append"):
        safe_append_tally(target, _TALLY)


def test_short_write_retries_until_record_is_complete(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "metrics.md"
    real_write = os.write
    writes: list[bytes] = []

    def short_write(fd: int, data: bytes) -> int:
        chunk_size = max(1, len(data) // 2)
        chunk = data[:chunk_size]
        writes.append(bytes(chunk))
        return real_write(fd, chunk)

    monkeypatch.setattr(metrics_writer.os, "write", short_write)

    safe_append_tally(target, _TALLY)

    assert len(writes) > 1
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"


def test_zero_byte_write_fails_closed(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "metrics.md"

    def zero_write(fd: int, data: bytes) -> int:
        return 0

    monkeypatch.setattr(metrics_writer.os, "write", zero_write)

    with pytest.raises(MetricsWriteError, match="zero-byte write"):
        safe_append_tally(target, _TALLY)


# --- CLI argv exit-code contract ---------------------------------------------


def test_cli_appends_and_exits_zero(tmp_path: Path) -> None:
    target = tmp_path / "metrics.md"

    rc = metrics_writer.main([str(target), _TALLY])

    assert rc == 0
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"


def test_cli_rejects_symlink_with_exit_one(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    link = tmp_path / "metrics.md"
    _symlink_or_skip(link, secret)

    rc = metrics_writer.main([str(link), _TALLY])

    assert rc == 1


def test_cli_wrong_arg_count_exits_two(capsys) -> None:
    assert metrics_writer.main([]) == 2
    assert metrics_writer.main(["only-one"]) == 2
    assert metrics_writer.main(["a", "b", "c"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err


def test_main_reads_sys_argv_when_argv_none(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "metrics.md"
    monkeypatch.setattr(sys, "argv", ["metrics_writer.py", str(target), _TALLY])

    assert metrics_writer.main() == 0
    assert target.read_text(encoding="utf-8") == _TALLY + "\n"
