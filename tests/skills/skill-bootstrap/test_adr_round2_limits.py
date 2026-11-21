"""Review round 2 tests for input limits: items 12 and 13."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import bootstrap_adr
import pytest
from adr_helpers import CLI, new_repo, run_cli
from adr_scan import ConfigError

needs_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes on this system")


def _fifo(tmp_path: Path) -> Path:
    path = tmp_path / "pipe.json"
    os.mkfifo(path)
    return path


def _run_with_timeout(*args: str) -> tuple[int, dict[str, object]]:
    """Run the CLI with a hard timeout, so a read that blocks fails the test and does not hang."""
    proc = subprocess.run(
        [sys.executable, "-B", str(CLI), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Item 13: the JSON reads refuse a non-regular file and read at most the limit plus one byte
# ---------------------------------------------------------------------------


@needs_fifo
def test_a_named_pipe_as_the_scan_file_is_refused_not_read(tmp_path: Path) -> None:
    code, payload = _run_with_timeout(
        "draft", "--scan", str(_fifo(tmp_path)), "--id", "c-1", "--out", str(tmp_path / "o")
    )
    assert code == 2 and payload["error"] == "config"
    assert "not a regular file" in str(payload["message"])


@needs_fifo
def test_a_named_pipe_as_the_pr_export_is_refused_not_read(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    code, payload = _run_with_timeout(
        "scan",
        "--repo",
        str(repo),
        "--prs-json",
        str(_fifo(tmp_path)),
        "--out",
        str(tmp_path / "scan.json"),
    )
    assert code == 2 and payload["error"] == "config"
    assert "not a regular file" in str(payload["message"])
    assert not (tmp_path / "scan.json").exists()


def test_a_directory_as_a_json_input_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a regular file|cannot read"):
        bootstrap_adr._read_json(str(tmp_path), "scan file")


def test_a_json_file_over_the_limit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap_adr, "MAX_JSON_BYTES", 10)
    big = tmp_path / "big.json"
    big.write_text('["abcdefghi"]', encoding="utf-8")
    with pytest.raises(ConfigError, match="too large"):
        bootstrap_adr._read_json(str(big), "scan file")


def test_a_json_file_at_the_limit_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap_adr, "MAX_JSON_BYTES", 10)
    exact = tmp_path / "exact.json"
    exact.write_text('["abcdef"]', encoding="utf-8")
    assert exact.stat().st_size == 10
    assert bootstrap_adr._read_json(str(exact), "scan file") == ["abcdef"]


@pytest.mark.skipif(not Path("/proc/self/status").is_file(), reason="needs procfs")
def test_the_limit_counts_bytes_read_not_the_size_the_file_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A procfs file is a regular file whose st_size is 0 and whose content is longer.
    monkeypatch.setattr(bootstrap_adr, "MAX_JSON_BYTES", 10)
    assert Path("/proc/self/status").stat().st_size == 0
    with pytest.raises(ConfigError, match="too large"):
        bootstrap_adr._read_json("/proc/self/status", "scan file")


def test_a_missing_json_file_is_still_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        bootstrap_adr._read_json(str(tmp_path / "nope.json"), "--prs-json")


def test_a_regular_json_file_still_parses(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text('{"a": [1, 2]}', encoding="utf-8")
    assert bootstrap_adr._read_json(str(path), "scan file") == {"a": [1, 2]}


# ---------------------------------------------------------------------------
# Item 12: --max-commits has a ceiling of 100,000
# ---------------------------------------------------------------------------


def test_a_max_commits_above_the_ceiling_exits_two_with_config(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    code, payload = run_cli(
        "scan",
        "--repo",
        str(repo),
        "--max-commits",
        "100001",
        "--out",
        str(tmp_path / "scan.json"),
    )
    assert code == 2 and payload["error"] == "config"
    assert "100000" in str(payload["message"])
    assert not (tmp_path / "scan.json").exists()


def test_the_ceiling_value_itself_is_accepted(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=a",
            "-c",
            "user.email=a@b.c",
            "commit",
            "-qm",
            "x",
        ],
        check=True,
    )
    code, payload = run_cli(
        "scan",
        "--repo",
        str(repo),
        "--max-commits",
        "100000",
        "--out",
        str(tmp_path / "scan.json"),
    )
    assert code == 0 and payload["max_commits"] == 100000
