"""File handling for a downloaded seed: no symlink follow, no overwrite, capped stream.

Issue #6239. The archive path writes the database through O_CREAT|O_EXCL|O_NOFOLLOW,
and the download streams into a fresh file with a size cap enforced while reading.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from scripts.validation import testmon_seed_archive as archive
from scripts.validation import testmon_seed_gh as gh_module

_EMIT = "import sys; sys.stdout.buffer.write(b'x' * int(sys.argv[1]))"
_COMMAND = (sys.executable, "-c", _EMIT)


def _download(destination: Path, size: int, cap: int = 1000) -> None:
    gh_module.download_to_file(str(size), destination, 30.0, cap, command=_COMMAND)


def test_a_download_streams_the_exact_bytes_into_a_private_file(tmp_path: Path) -> None:
    _download(tmp_path / "seed.zip", 500)
    assert (tmp_path / "seed.zip").read_bytes() == b"x" * 500
    assert stat.S_IMODE((tmp_path / "seed.zip").stat().st_mode) == 0o600


def test_a_download_over_the_cap_is_refused_while_streaming(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="size cap"):
        _download(tmp_path / "seed.zip", 5000, cap=1000)


def test_a_download_never_overwrites_or_follows_an_existing_path(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    link = tmp_path / "seed.zip"
    link.symlink_to(victim)
    with pytest.raises(FileExistsError):
        _download(link, 10)
    assert victim.read_text(encoding="utf-8") == "keep"
    existing = tmp_path / "existing.zip"
    existing.write_bytes(b"mine")
    with pytest.raises(FileExistsError):
        _download(existing, 10)
    assert existing.read_bytes() == b"mine"


def test_a_failing_or_slow_child_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exit"):
        gh_module.download_to_file(
            "x", tmp_path / "a", 30.0, 10, command=(sys.executable, "-c", "raise SystemExit(3)")
        )
    with pytest.raises(TimeoutError):
        gh_module.download_to_file(
            "x",
            tmp_path / "b",
            0.3,
            10,
            command=(sys.executable, "-c", "import time; time.sleep(30)"),
        )


def test_the_database_is_written_through_a_private_staging_file(tmp_path: Path) -> None:
    archive.write_database(tmp_path, archive.SQLITE_MAGIC + b"data")
    target = tmp_path / ".testmondata"
    assert target.read_bytes() == archive.SQLITE_MAGIC + b"data"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_a_planted_symlink_at_the_staging_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive.secrets, "token_hex", lambda _n: "fixed")
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    (tmp_path / ".testmondata.seed.fixed.tmp").symlink_to(victim)
    with pytest.raises(FileExistsError):
        archive.write_database(tmp_path, archive.SQLITE_MAGIC)
    assert victim.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / ".testmondata").exists()


def test_the_staging_open_uses_exclusive_nofollow_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    real_open = os.open

    def spy(path: str | Path, flags: int, mode: int = 0o777) -> int:
        seen.append(flags)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", spy)
    archive.write_database(tmp_path, archive.SQLITE_MAGIC)
    assert seen[0] & os.O_EXCL
    assert seen[0] & os.O_CREAT
    assert seen[0] & getattr(os, "O_NOFOLLOW", 0)
