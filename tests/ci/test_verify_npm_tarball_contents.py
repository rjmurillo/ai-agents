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
)

GOOD = {
    "package/package.json": b"{}",
    "package/README.md": b"# readme",
    "package/LICENSE": b"MIT",
    "package/dist/cli.js": b"//cli",
    "package/bundle/assets/CLAUDE.md": b"top",
    "package/bundle/assets/agents/analyst.md": b"agent",
    "package/bundle/assets/skills/spec/SKILL.md": b"skill",
    "package/bundle/assets/rules/universal.md": b"rule",
}


def _pack(
    directory: Path,
    files: dict[str, bytes],
    name: str = "pkg-0.7.0.tgz",
    *,
    kinds: dict[str, bytes] | None = None,
) -> Path:
    """Write a real .tgz. ``kinds`` maps a member name to a tarfile type byte."""
    path = directory / name
    kinds = kinds or {}
    with tarfile.open(path, "w:gz") as archive:
        for member_name, data in files.items():
            info = tarfile.TarInfo(member_name)
            kind = kinds.get(member_name)
            if kind == tarfile.DIRTYPE:
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == tarfile.SYMTYPE:
                info.type = tarfile.SYMTYPE
                info.linkname = "elsewhere"
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return path


def _without(prefix: str) -> dict[str, bytes]:
    return {k: v for k, v in GOOD.items() if not k.startswith(prefix)}


def test_a_tarball_with_every_required_entry_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pack(tmp_path, GOOD)
    assert main(["--dir", str(tmp_path)]) == EXIT_OK
    assert "4 in bundle/assets/" in capsys.readouterr().out


def test_a_tarball_without_bundle_assets_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pack(tmp_path, _without("package/bundle/"))
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING
    assert "package/bundle/assets/agents/" in capsys.readouterr().err


@pytest.mark.parametrize("tree", ["agents", "skills", "rules"])
def test_each_kit_tree_is_enforced_even_when_top_level_assets_exist(
    tmp_path: Path, tree: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _pack(tmp_path, _without(f"package/bundle/assets/{tree}/"))
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING
    assert f"package/bundle/assets/{tree}/" in capsys.readouterr().err


def test_a_directory_member_under_a_kit_tree_does_not_count(tmp_path: Path) -> None:
    files = _without("package/bundle/assets/rules/")
    files["package/bundle/assets/rules/universal.md"] = b""
    _pack(
        tmp_path,
        files,
        kinds={"package/bundle/assets/rules/universal.md": tarfile.DIRTYPE},
    )
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


def test_an_empty_kit_file_does_not_count(tmp_path: Path) -> None:
    files = dict(GOOD)
    files["package/bundle/assets/rules/universal.md"] = b""
    _pack(tmp_path, files)
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.DIRTYPE])
def test_a_link_or_directory_in_place_of_cli_js_fails(tmp_path: Path, kind: bytes) -> None:
    _pack(tmp_path, GOOD, kinds={"package/dist/cli.js": kind})
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


def test_an_empty_cli_js_fails(tmp_path: Path) -> None:
    files = dict(GOOD)
    files["package/dist/cli.js"] = b""
    _pack(tmp_path, files)
    assert main(["--dir", str(tmp_path)]) == EXIT_MISSING


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
