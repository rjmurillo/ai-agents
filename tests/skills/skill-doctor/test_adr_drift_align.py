"""adr_drift.py align handling: detect by default, run only `align adr` on opt-in."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import adr_drift
import pytest
from adr_drift_helpers import scan, seeded_repo

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the align shim is a POSIX script")

SHIM = """#!/bin/sh
{{
  for arg in "$@"; do printf 'arg=%s\\n' "$arg"; done
  printf 'DO_NOT_TRACK=%s\\n' "$DO_NOT_TRACK"
  if read -r _line; then printf 'stdin_data=1\\n'; else printf 'stdin_data=0\\n'; fi
  printf 'cwd=%s\\n' "$PWD"
}} >> "$ALIGN_LOG"
{body}
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path: Path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("ALIGN_LOG", str(tmp_path / "align.log"))
    return path


def _path_without_align(tmp_path: Path, monkeypatch, shim_body: str | None) -> Path:
    """PATH holding git and, optionally, a fake `align`. Returns the log path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = shutil.which("git")
    assert git is not None
    (bin_dir / "git").symlink_to(git)
    sleep = shutil.which("sleep")
    assert sleep is not None
    (bin_dir / "sleep").symlink_to(sleep)
    if shim_body is not None:
        shim = bin_dir / "align"
        shim.write_text(SHIM.format(body=shim_body), encoding="utf-8")
        shim.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return tmp_path / "align.log"


def _graph(home: Path) -> None:
    (home / ".align").mkdir()
    (home / ".align" / "local.db").write_bytes(b"")


def test_align_absent_still_gives_a_complete_scan_with_exit_0(tmp_path, capsys, monkeypatch, home):
    repo = seeded_repo(tmp_path / "repo")
    _path_without_align(tmp_path, monkeypatch, None)

    result = scan(capsys, repo)

    assert result["align"]["status"] == "absent"
    assert result["counts"]["total"] == len(result["findings"])


def test_align_on_path_is_not_called_without_the_flag(tmp_path, capsys, monkeypatch, home):
    repo = seeded_repo(tmp_path / "repo")
    log = _path_without_align(tmp_path, monkeypatch, "echo should-not-run")
    _graph(home)

    result = scan(capsys, repo)

    assert result["align"]["status"] == "detected"
    assert result["align"]["command_hint"] == "DO_NOT_TRACK=1 align adr"
    assert not log.exists()


def test_flag_without_a_graph_does_not_call_align(tmp_path, capsys, monkeypatch, home):
    repo = seeded_repo(tmp_path / "repo")
    log = _path_without_align(tmp_path, monkeypatch, "echo should-not-run")

    result = scan(capsys, repo, "--with-align")

    assert result["align"]["status"] == "no_graph" and not log.exists()


def test_flag_with_a_graph_runs_align_adr_only_with_telemetry_off(
    tmp_path, capsys, monkeypatch, home
):
    repo = seeded_repo(tmp_path / "repo")
    log = _path_without_align(tmp_path, monkeypatch, "echo 'ADR-001 listed'")
    _graph(home)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)

    result = scan(capsys, repo, "--with-align")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert [ln for ln in lines if ln.startswith("arg=")] == ["arg=adr"]
    assert "DO_NOT_TRACK=1" in lines and "stdin_data=0" in lines
    assert f"cwd={repo.resolve()}" in lines
    assert "arg=write" not in lines
    assert result["align"]["status"] == "ran" and "ADR-001 listed" in result["align"]["text"]
    assert "does not recognize" in result["align"]["advisory_note"]


def test_align_output_never_changes_findings_or_counts(tmp_path, capsys, monkeypatch, home):
    repo = seeded_repo(tmp_path / "repo")
    _path_without_align(tmp_path, monkeypatch, "echo 'ADR-999 missing everywhere'")
    _graph(home)

    plain = scan(capsys, repo, name="plain.json")
    with_align = scan(capsys, repo, "--with-align", name="aligned.json")

    assert plain["findings"] == with_align["findings"] and plain["counts"] == with_align["counts"]


def test_align_nonzero_exit_is_reported_as_failed_with_the_stderr_tail(
    tmp_path, capsys, monkeypatch, home
):
    repo = seeded_repo(tmp_path / "repo")
    _path_without_align(tmp_path, monkeypatch, "echo 'boom reason' >&2; exit 3")
    _graph(home)

    result = scan(capsys, repo, "--with-align")

    assert result["align"]["status"] == "failed" and result["align"]["exit_code"] == 3
    assert "boom reason" in result["align"]["text"]


def test_align_timeout_is_reported_as_failed(tmp_path, capsys, monkeypatch, home):
    repo = seeded_repo(tmp_path / "repo")
    _path_without_align(tmp_path, monkeypatch, "sleep 5")
    _graph(home)
    monkeypatch.setattr(adr_drift, "ALIGN_TIMEOUT_SECONDS", 1)

    result = scan(capsys, repo, "--with-align")

    assert result["align"]["status"] == "failed" and "timed out" in result["align"]["text"]


def test_the_default_timeout_is_sixty_seconds():
    assert adr_drift.ALIGN_TIMEOUT_SECONDS == 60
