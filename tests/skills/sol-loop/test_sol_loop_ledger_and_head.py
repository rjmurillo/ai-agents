"""Run-log integrity and the reviewed revision: ledger validation, exclusive writes, head SHA."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from _sol_loop_helpers import (
    _commit_file,
    _gate,
    _git_repo,
    _head,
    _log_dir,
    _logs,
    _out,
    _record,
    _reply,
    _touch_after_head,
    mod,
)

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")
GOOD_RUN = {
    "status": "ok",
    "key": "b",
    "counts": {"raw": 3, "kept": 2, "dropped": 1, "sol_only": 1, "overlap": 1},
    "findings": [{"id": "S1", "sol_only": True, "outcome": "fixed"}],
}


def _summarize(tmp_path, capsys):
    code = mod.main(["summarize", "--repo", str(tmp_path), "--log-base", str(tmp_path)])
    return code, _out(capsys)


def _write_runs(tmp_path, **runs):
    log_dir = _log_dir(tmp_path)
    log_dir.mkdir(parents=True)
    for name, record in runs.items():
        (log_dir / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")


# Ledger validation


def test_summarize_counts_malformed_records_as_unreadable(tmp_path, capsys):
    _write_runs(
        tmp_path,
        good=GOOD_RUN,
        findings_null={"status": "ok", "findings": None},
        counts_list={"status": "ok", "counts": [1]},
    )

    code, totals = _summarize(tmp_path, capsys)

    assert code == mod.EXIT_OK
    assert (totals["runs"], totals["unreadable"]) == (1, 2)
    assert (totals["ok"], totals["kept"], totals["sol_only"]) == (1, 2, 1)
    assert totals["sol_only_outcomes"]["fixed"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"dropped": "none"},
        {"findings": {"id": "S1"}},
        {"counts": "3"},
        {"counts": {"kept": "2"}},
        {"counts": {"kept": True}},
        {"counts": {"kept": 1.5}},
    ],
)
def test_summarize_rejects_each_malformed_shape(tmp_path, capsys, bad):
    _write_runs(tmp_path, bad={"status": "ok", **bad})

    code, totals = _summarize(tmp_path, capsys)

    assert code == mod.EXIT_OK
    assert (totals["runs"], totals["unreadable"]) == (0, 1)


def test_summarize_accepts_absent_and_null_count_values(tmp_path, capsys):
    _write_runs(
        tmp_path,
        bare={"status": "skipped"},
        nulls={
            "status": "ok",
            "counts": {"kept": None, "dropped": 2},
            "findings": [],
            "dropped": [],
        },
    )

    code, totals = _summarize(tmp_path, capsys)

    assert code == mod.EXIT_OK
    assert (totals["runs"], totals["unreadable"], totals["dropped"]) == (2, 0, 2)


# Exclusive log creation


def _run_record(key="feature/a", **extra):
    return {"timestamp": "2026-01-01T00:00:00Z", "key": key, "round": 1, "status": "ok", **extra}


def test_write_run_log_never_overwrites_a_file_even_when_exists_lies(tmp_path, monkeypatch):
    ledger = sys.modules["sol_ledger"]
    first = ledger.write_run_log(_run_record(n=1), tmp_path)
    before = first.read_text(encoding="utf-8")
    monkeypatch.setattr(Path, "exists", lambda self: False)  # simulate losing the race

    second = ledger.write_run_log(_run_record(n=2), tmp_path)

    assert second is not None and second != first
    assert first.read_text(encoding="utf-8") == before
    assert json.loads(second.read_text(encoding="utf-8"))["n"] == 2


def test_branches_that_share_a_label_get_separate_log_files(tmp_path):
    ledger = sys.modules["sol_ledger"]

    first = ledger.write_run_log(_run_record("feature/a"), tmp_path)
    second = ledger.write_run_log(_run_record("feature-a"), tmp_path)

    assert first != second
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_write_run_log_still_returns_none_on_other_os_errors(tmp_path, capsys):
    ledger = sys.modules["sol_ledger"]
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    assert ledger.write_run_log(_run_record(), blocker / "logs") is None
    assert "run log not written" in capsys.readouterr().err


# Reviewed head


@_needs_git
def test_gate_proceed_payload_names_the_head_sha(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)

    code = _gate(tmp_path, critic_file, repo=repo)

    out = _out(capsys)
    assert code == mod.EXIT_OK
    assert out["head_sha"] == _head(repo) and len(out["head_sha"]) == 40


@_needs_git
def test_record_without_the_flag_logs_current_head_only(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)

    code = _record(tmp_path, critic_file, _reply(tmp_path), repo=repo)

    out = _out(capsys)
    log = _logs(tmp_path)[0]
    assert code == mod.EXIT_OK
    assert log["head_sha"] == _head(repo)
    assert "head_at_record" not in log and "head_moved" not in out


@_needs_git
def test_record_with_reviewed_head_equal_to_head_adds_no_head_at_record(
    tmp_path, critic_file, capsys
):
    repo = tmp_path / "repo"
    _git_repo(repo)
    head = _head(repo)

    code = _record(tmp_path, critic_file, _reply(tmp_path), "--reviewed-head", head, repo=repo)

    out = _out(capsys)
    log = _logs(tmp_path)[0]
    assert code == mod.EXIT_OK
    assert log["head_sha"] == head
    assert "head_at_record" not in log and "head_moved" not in out


@_needs_git
def test_record_after_a_new_commit_keeps_the_reviewed_sha(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    reviewed = _head(repo)
    _commit_file(repo, "later.py")
    moved = _head(repo)
    abbreviated = reviewed[:10]

    code = _record(
        tmp_path, critic_file, _reply(tmp_path), "--reviewed-head", abbreviated, repo=repo
    )

    out = _out(capsys)
    log = _logs(tmp_path)[0]
    assert moved != reviewed and code == mod.EXIT_OK
    assert (log["head_sha"], log["head_at_record"]) == (reviewed, moved)
    assert out["head_moved"] is True


@_needs_git
@pytest.mark.parametrize("bad", ["not-a-sha", "--all", "0" * 40])
def test_record_refuses_a_reviewed_head_that_is_not_a_commit(tmp_path, critic_file, capsys, bad):
    repo = tmp_path / "repo"
    _git_repo(repo)

    code = _record(tmp_path, critic_file, _reply(tmp_path), f"--reviewed-head={bad}", repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "is not a commit" in capsys.readouterr().err
    assert _logs(tmp_path) == []
