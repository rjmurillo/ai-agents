"""Tests for the subprocess encoding count ratchet (issue #4261)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.ci import subprocess_encoding_count_ratchet as ratchet


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), *args], check=True)


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


def test_current_count_counts_checker_findings(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "bad.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], capture_output=True, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "good.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], capture_output=True, encoding='utf-8', errors='replace')\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "scripts/bad.py", "scripts/good.py")

    assert ratchet.current_count(tmp_path) == 1


def test_current_count_counts_pipe_captures_and_aliases(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "bad_stdout.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], stdout=subprocess.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_alias.py").write_text(
        "from subprocess import PIPE as CAPTURE, run as srun\n"
        "srun(['x'], stderr=CAPTURE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_module_alias.py").write_text(
        "import subprocess as sp\n"
        "sp.run(['x'], stderr=sp.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_assigned_module_alias.py").write_text(
        "import subprocess\n"
        "sp = subprocess\n"
        "sp.run(['x'], stdout=sp.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "good_binary.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], stdout=subprocess.PIPE)\n",
        encoding="utf-8",
    )
    _git(
        tmp_path,
        "add",
        "scripts/bad_stdout.py",
        "scripts/bad_alias.py",
        "scripts/bad_module_alias.py",
        "scripts/bad_assigned_module_alias.py",
        "scripts/good_binary.py",
    )

    assert ratchet.current_count(tmp_path) == 4


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
