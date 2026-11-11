"""verify_npm_tarball_contents.py: a packed CLI tarball must carry the kit (issue #7217)."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from scripts.ci.verify_npm_tarball_contents import (
    EXIT_MISSING,
    EXIT_OK,
    EXIT_UNREADABLE,
    main,
    missing_entries,
)

GOOD = {
    "package/package.json": b"{}",
    "package/README.md": b"# readme",
    "package/LICENSE": b"MIT",
    "package/dist/cli.js": b"//cli",
    "package/bundle/assets/agents/analyst.md": b"agent",
}


def _pack(directory: Path, files: dict[str, bytes], name: str = "pkg-0.7.0.tgz") -> Path:
    path = directory / name
    with tarfile.open(path, "w:gz") as archive:
        for member_name, data in files.items():
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_a_tarball_with_every_required_entry_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pack(tmp_path, GOOD)
    assert main(["--dir", str(tmp_path)]) == EXIT_OK
    assert "1 in bundle/assets/" in capsys.readouterr().out


def test_a_tarball_without_bundle_assets_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {k: v for k, v in GOOD.items() if "bundle/assets" not in k}
    _pack(tmp_path, files)
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING
    assert "bundle/assets/" in capsys.readouterr().err


def test_an_assets_directory_entry_with_no_file_does_not_count(tmp_path: Path) -> None:
    files = {k: v for k, v in GOOD.items() if "bundle/assets" not in k}
    assert missing_entries([*files, "package/bundle/assets/"]) == [
        "package/bundle/assets/* (at least one file)"
    ]


@pytest.mark.parametrize(
    "absent",
    ["package/dist/cli.js", "package/README.md", "package/LICENSE", "package/package.json"],
)
def test_each_required_file_is_enforced(tmp_path: Path, absent: str) -> None:
    _pack(tmp_path, {k: v for k, v in GOOD.items() if k != absent})
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


def test_an_empty_directory_fails_because_nothing_was_examined(tmp_path: Path) -> None:
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


def test_two_tarballs_fail_because_the_choice_is_ambiguous(tmp_path: Path) -> None:
    _pack(tmp_path, GOOD, "a.tgz")
    _pack(tmp_path, GOOD, "b.tgz")
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


def test_a_corrupt_tarball_exits_unreadable(tmp_path: Path) -> None:
    (tmp_path / "bad.tgz").write_bytes(b"not a gzip stream")
    assert main(["--dir", str(tmp_path)]) == EXIT_UNREADABLE
