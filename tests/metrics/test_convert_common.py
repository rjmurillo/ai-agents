"""Tests for scripts/metrics/convert_common.py."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from scripts.metrics.convert_common import safe_session_id, write_private


@pytest.mark.parametrize("value", ["abc", "0a1b-2c.3_d", "a" * 128])
def test_safe_session_id_accepts_plain_ids(value: str) -> None:
    assert safe_session_id(value) == value


@pytest.mark.parametrize(
    "value", ["", "../x", "a/b", ".hidden", "-lead", "a b", "a\n", "a" * 129, None, 7]
)
def test_safe_session_id_rejects_hostile_values(value: object) -> None:
    assert safe_session_id(value) is None


def test_write_private_sets_mode_and_replaces_file(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o644)
    write_private(path, "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_private_replaces_symlink_without_following_it(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    path = tmp_path / "f.jsonl"
    path.symlink_to(victim)
    write_private(path, "new")
    assert victim.read_text(encoding="utf-8") == "keep"
    assert not path.is_symlink()
    assert path.read_text(encoding="utf-8") == "new"


def test_write_private_replaces_dangling_symlink(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.symlink_to(tmp_path / "missing-target")
    write_private(path, "new")
    assert not (tmp_path / "missing-target").exists()
    assert path.read_text(encoding="utf-8") == "new"
