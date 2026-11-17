"""Git-backed sol-loop checks: critic staleness and the per-branch round count."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import types
from pathlib import Path

import pytest
from _sol_loop_helpers import (
    _argv,
    _commit_file,
    _gate,
    _git_repo,
    _git_run,
    _logs,
    _out,
    _record,
    _reply,
    _set_mtime,
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


@_needs_git
@pytest.mark.parametrize(
    ("rel", "remove_dir"), [("app.py", False), ("pkg/mod.py", False), ("pkg/mod.py", True)]
)
def test_gate_refuses_critic_older_than_a_deleted_tracked_file(
    tmp_path, critic_file, capsys, rel, remove_dir
):
    repo = tmp_path / "repo"
    _git_repo(repo)
    victim = _commit_file(repo, rel)
    _touch_after_head(critic_file)
    victim.unlink()
    if remove_dir:
        victim.parent.rmdir()
    # Deleting a file updates its nearest existing parent directory.
    bumped = victim.parent if victim.parent.is_dir() else repo
    _set_mtime(bumped, critic_file.stat().st_mtime + 5)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "uncommitted change" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_the_file_was_deleted_before_the_critic(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    victim = _commit_file(repo, "app.py")
    _touch_after_head(critic_file)
    victim.unlink()
    _set_mtime(repo, critic_file.stat().st_mtime - 100)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


def _rename_with_old_mtime(repo, critic_file, mode, bumped):
    """Move pkg/a.py to other/b.py keeping its old mtime; bump one directory's mtime."""
    source = _commit_file(repo, "pkg/a.py")
    _set_mtime(source, 1_000_000)
    (repo / "other").mkdir()
    _touch_after_head(critic_file)
    critic_time = critic_file.stat().st_mtime
    if mode == "git mv":
        _git_run(repo, "mv", "pkg/a.py", "other/b.py")
    else:
        source.rename(repo / "other" / "b.py")
    for directory in (repo, repo / "pkg", repo / "other"):
        _set_mtime(directory, critic_time - 100)
    if bumped:
        _set_mtime(repo / bumped, critic_time + 5)


@_needs_git
# A plain mv shows as a delete plus an untracked file, so only the source directory is
# a trace there; a staged rename also counts the destination directory.
@pytest.mark.parametrize(
    ("mode", "bumped"), [("git mv", "pkg"), ("git mv", "other"), ("mv", "pkg")]
)
def test_gate_refuses_critic_older_than_a_rename_that_kept_its_old_mtime(
    tmp_path, critic_file, capsys, mode, bumped
):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _rename_with_old_mtime(repo, critic_file, mode, bumped)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "uncommitted change" in capsys.readouterr().err


@_needs_git
@pytest.mark.parametrize("mode", ["git mv", "mv"])
def test_gate_proceeds_when_the_rename_predates_the_critic(tmp_path, critic_file, capsys, mode):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _rename_with_old_mtime(repo, critic_file, mode, bumped="")

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


def _checkout_older_commit(repo):
    """Commit A then B with old dates, then check A out; HEAD moves now, to an old commit."""
    _commit_file(repo, "a.py", when="2020-01-01T00:00:00Z")
    first = _git_run(repo, "rev-parse", "HEAD")
    _commit_file(repo, "b.py", when="2020-01-02T00:00:00Z")
    _git_run(repo, "checkout", "-q", "--detach", first)


@_needs_git
def test_gate_refuses_a_critic_written_before_a_checkout_of_an_older_commit(
    tmp_path, critic_file, capsys
):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _commit_file(repo, "a.py", when="2020-01-01T00:00:00Z")
    first = _git_run(repo, "rev-parse", "HEAD")
    _commit_file(repo, "b.py", when="2020-01-02T00:00:00Z")
    _set_mtime(critic_file, time.time() - 100)  # after both commit times, before the checkout
    _git_run(repo, "checkout", "-q", "--detach", first)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "older than HEAD" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_the_critic_is_written_after_the_checkout(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _checkout_older_commit(repo)
    _touch_after_head(critic_file)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


def _review_with_brief_in_repo(tmp_path, critic_file, monkeypatch, *, source_change):
    """Run ``review`` with the brief inside the checkout and newer than the critic."""
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    later = critic_file.stat().st_mtime + 5
    brief = repo / "brief.md"
    brief.write_text("Review only.\n", encoding="utf-8")
    _set_mtime(brief, later)
    if source_change:
        fix = repo / "app.py"
        fix.write_text("x = 2\n", encoding="utf-8")
        _set_mtime(fix, later + 5)
    calls = []

    def fake_run_sol(runner, model, text, cwd, timeout):
        calls.append(runner)
        return types.SimpleNamespace(ok=True, text="VERDICT: APPROVE\n")

    monkeypatch.setattr(mod, "available_runner", lambda: "codex")
    monkeypatch.setattr(mod, "run_sol", fake_run_sol)
    argv = _argv("review", tmp_path, critic_file, "--brief-file", str(brief), repo=repo)
    return mod.main(argv), calls


@_needs_git
def test_review_brief_inside_the_checkout_does_not_make_the_critic_stale(
    tmp_path, critic_file, monkeypatch
):
    code, calls = _review_with_brief_in_repo(
        tmp_path, critic_file, monkeypatch, source_change=False
    )

    assert code == mod.EXIT_OK
    assert calls == ["codex"]


@_needs_git
def test_review_still_refuses_a_source_change_made_after_the_critic(
    tmp_path, critic_file, monkeypatch, capsys
):
    code, calls = _review_with_brief_in_repo(tmp_path, critic_file, monkeypatch, source_change=True)

    assert code == mod.EXIT_CONFIG
    assert calls == []
    assert "uncommitted change" in capsys.readouterr().err


def test_committed_first_run_records_a_fixed_sol_only_catch():
    root = Path(__file__).resolve().parents[3]

    totals = mod.summarize(root / ".project-toolkit" / "metrics" / "sol-loop")

    assert totals["unreadable"] == 0
    assert totals["sol_only_outcomes"]["fixed"] >= 1


def _commit(repo: Path, name: str) -> Path:
    path = repo / name
    path.write_text("x = 1\n", encoding="utf-8")
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    for args in (["add", name], [*identity, "commit", "-q", "-m", "add"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return path


@_needs_git
def test_modified_tracked_file_newer_than_critic_is_caught(tmp_path, critic_file, capsys):
    # Regression for Sol round 1 S1: porcelain lines start with a space (" M app.py").
    repo = tmp_path / "repo"
    _git_repo(repo)
    tracked = _commit(repo, "app.py")
    _touch_after_head(critic_file)
    tracked.write_text("x = 2\n", encoding="utf-8")
    later = critic_file.stat().st_mtime + 5
    os.utime(tracked, (later, later))

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "uncommitted change" in capsys.readouterr().err


@_needs_git
def test_record_accepts_a_reply_saved_inside_the_checkout(tmp_path, critic_file, capsys):
    # Regression for Sol round 1 S2: record runs after Sol, so it does not re-check freshness.
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    assert _gate(tmp_path, critic_file, repo=repo) == mod.EXIT_OK
    reply = repo / "reply.md"
    reply.write_text("VERDICT: APPROVE\n", encoding="utf-8")
    later = critic_file.stat().st_mtime + 5
    os.utime(reply, (later, later))

    code = mod.main(_argv("record", tmp_path, critic_file, "--reply", str(reply), repo=repo))

    assert code == mod.EXIT_OK


@_needs_git
def test_record_stores_repo_relative_paths(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    reply = tmp_path / "reply.md"
    target = (repo / "pkg" / "mod.py").resolve()
    reply.write_text(
        f"VERDICT: CHANGES\nS1 [should] [mod.py:3]({target}:3) bug. Repro: run it.\n",
        encoding="utf-8",
    )

    mod.main(_argv("record", tmp_path, critic_file, "--reply", str(reply), repo=repo))

    assert _logs(tmp_path)[0]["findings"][0]["file"] == "pkg/mod.py"
