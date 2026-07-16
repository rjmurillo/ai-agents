"""Tests for the whole-repo ruff count ratchet (issue #2993)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_count_ratchet as ratchet


def _fake_ruff(returncode: int, violation_lines: int):
    """Return a subprocess.run stand-in emitting N json-lines violations."""

    def _run(cmd, **kwargs):  # noqa: ANN001, ANN003
        stdout = "".join('{"code":"E501"}\n' for _ in range(violation_lines))
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def _write_baseline(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "ruff_count_baseline.txt"
    path.write_text(value, encoding="utf-8")
    return path


def test_count_equal_to_baseline_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(1, 408))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_count_above_baseline_is_regression(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(1, 409))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_REGRESSION


def test_count_below_baseline_passes_without_updating(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(1, 400))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "408"


def test_count_below_baseline_with_update_lowers_baseline(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(0, 400))
    rc = ratchet.main(
        ["--baseline", str(baseline), "--repo-root", str(tmp_path), "--update"]
    )
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "400"


def test_clean_tree_zero_count_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "0")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(0, 0))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_missing_baseline_is_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_ruff(1, 408))
    rc = ratchet.main(
        ["--baseline", str(tmp_path / "absent.txt"), "--repo-root", str(tmp_path)]
    )
    assert rc == ratchet.EXIT_CONFIG


def test_malformed_baseline_is_config_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "not-a-number")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(1, 408))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


def test_ruff_crash_is_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_ruff(2, 0))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
