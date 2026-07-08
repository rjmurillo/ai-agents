from __future__ import annotations

from pathlib import Path

import pytest

from scripts.hook_utilities.path_safety import validate_path_no_traversal


def test_valid_relative_path_resolves_inside_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "safe.txt"
    target.write_text("safe\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    assert validate_path_no_traversal(Path("safe.txt")) == target.resolve()


def test_traversal_attempt_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    with pytest.raises(PermissionError, match="prohibited"):
        validate_path_no_traversal(Path("../outside.txt"))


def test_relative_symlink_escape_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = repo / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    monkeypatch.chdir(repo)

    with pytest.raises(PermissionError, match="outside the working directory"):
        validate_path_no_traversal(Path("link.txt"))


def test_absolute_path_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "absolute.txt"
    target.write_text("safe\n", encoding="utf-8")

    assert validate_path_no_traversal(target) == target.resolve()
