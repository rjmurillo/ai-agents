"""Tests for the subprocess encoding count ratchet (issue #4261)."""

from __future__ import annotations

from pathlib import Path

from scripts.ci import subprocess_encoding_count_ratchet as ratchet


def _write_baseline(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "subprocess_encoding_count_baseline.txt"
    path.write_text(value, encoding="utf-8")
    return path


def test_count_equal_to_baseline_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "5")
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 5)
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_count_above_baseline_is_regression(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "5")
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 6)
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_REGRESSION


def test_missing_baseline_is_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 5)
    rc = ratchet.main(["--baseline", str(tmp_path / "absent.txt"), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

