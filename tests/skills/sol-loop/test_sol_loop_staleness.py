"""Git-backed sol-loop checks: critic staleness and the per-branch round count."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sol_loop_helpers import (
    _argv,
    _gate,
    _git_repo,
    _logs,
    _out,
    _record,
    _reply,
    _touch_after_head,
    mod,
)

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")


@_needs_git
def test_gate_refuses_critic_output_older_than_head(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    os.utime(critic_file, (1_000_000, 1_000_000))

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "older than HEAD" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_critic_output_is_newer_than_head(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


@_needs_git
def test_round_count_is_per_branch_even_when_pr_number_appears(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    _record(tmp_path, critic_file, _reply(tmp_path), repo=repo)
    _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "7", repo=repo)
    capsys.readouterr()

    code = _gate(tmp_path, critic_file, "--pr", "7", repo=repo)

    assert code == mod.EXIT_ESCALATE
    assert len({log["key"] for log in _logs(tmp_path)}) == 1


@_needs_git
def test_gate_refuses_critic_older_than_an_uncommitted_fix(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    fix = repo / "app.py"
    fix.write_text("x = 1\n", encoding="utf-8")
    later = critic_file.stat().st_mtime + 5
    os.utime(fix, (later, later))

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "uncommitted change" in capsys.readouterr().err


@_needs_git
def test_untracked_run_logs_in_the_repo_do_not_make_the_critic_stale(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    argv = _argv("record", repo, critic_file, "--reply", str(_reply(tmp_path)), repo=repo)
    assert mod.main(argv) == mod.EXIT_OK
    capsys.readouterr()

    code = mod.main(_argv("gate", repo, critic_file, "--route", "t3", repo=repo))

    assert code == mod.EXIT_OK
    assert _out(capsys)["round"] == 2


def test_committed_first_run_records_a_fixed_sol_only_catch():
    root = Path(__file__).resolve().parents[3]

    totals = mod.summarize(root / ".project-toolkit" / "metrics" / "sol-loop")

    assert totals["unreadable"] == 0
    assert totals["sol_only_outcomes"]["fixed"] >= 1
