"""Regression tests for the review-pass fixes: symlink identity, inherited git
variables, review skip switches, atomic outcome writes, and same-second HEAD moves.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
from _sol_loop_helpers import (
    _argv,
    _commit_file,
    _gate,
    _git_repo,
    _git_run,
    _head,
    _log_dir,
    _logs,
    _out,
    _record,
    _reply,
    _set_mtime,
    _touch_after_head,
    mod,
)

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")


def _symlink_repo(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """A repo with files x and y and a committed symlink ``link`` to x."""
    if os.utime not in os.supports_follow_symlinks:
        pytest.skip("this platform cannot set a symlink's own mtime")
    repo = tmp_path / "repo"
    _git_repo(repo)
    x = _commit_file(repo, "x.txt")
    y = _commit_file(repo, "y.txt")
    link = repo / "link"
    try:
        link.symlink_to("x.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported here")
    _git_run(repo, "add", "link")
    _git_run(repo, "commit", "-q", "-m", "add link")
    return repo, link, x, y


def _retarget(link: Path, target: str, when: float | None = None) -> None:
    """Replace the symlink with a new one; ``when`` pins the new link's own mtime."""
    link.unlink()
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported here")
    if when is not None:
        os.utime(link, (when, when), follow_symlinks=False)


# A: symlink identity


@_needs_git
def test_gate_refuses_critic_older_than_a_symlink_retargeted_to_an_old_file(
    tmp_path, critic_file, capsys
):
    repo, link, x, y = _symlink_repo(tmp_path)
    _touch_after_head(critic_file)
    critic_time = critic_file.stat().st_mtime
    _set_mtime(x, critic_time - 100)
    _set_mtime(y, critic_time - 100)
    _retarget(link, "y.txt", critic_time + 5)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "uncommitted change" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_the_symlink_was_retargeted_before_the_critic(
    tmp_path, critic_file, capsys
):
    repo, link, x, y = _symlink_repo(tmp_path)
    _retarget(link, "y.txt")
    _touch_after_head(critic_file)
    critic_time = critic_file.stat().st_mtime
    _set_mtime(x, critic_time - 100)
    _set_mtime(y, critic_time - 100)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


# B: inherited git variables


@_needs_git
def test_gate_reads_the_repo_it_was_given_not_an_inherited_git_dir(
    tmp_path, critic_file, capsys, monkeypatch
):
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    _git_repo(repo_a)
    _git_repo(repo_b)
    _commit_file(repo_b, "b.py")
    head_a = _head(repo_a)
    assert head_a != _head(repo_b)
    _touch_after_head(critic_file)
    monkeypatch.setenv("GIT_DIR", str(repo_b / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo_b))

    code = _gate(tmp_path, critic_file, repo=repo_a)

    assert code == mod.EXIT_OK
    assert _out(capsys)["head_sha"] == head_a


def test_git_env_drops_repo_redirecting_variables_and_keeps_the_rest(monkeypatch):
    git_mod = sys.modules["sol_git"]
    for name in git_mod._GIT_REPO_VARS:
        monkeypatch.setenv(name, "/elsewhere")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/ceiling")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")

    env = git_mod._git_env()

    assert not git_mod._GIT_REPO_VARS & env.keys()
    assert env["GIT_CEILING_DIRECTORIES"] == "/ceiling"
    assert env["GIT_CONFIG_COUNT"] == "0"


# C: review honors the skip switches


@pytest.mark.parametrize(("switch", "author"), [("off", "anthropic"), (None, "openai")])
def test_review_skips_without_calling_sol(
    tmp_path, critic_file, capsys, monkeypatch, switch, author
):
    if switch:
        monkeypatch.setenv("AI_AGENTS_SOL_PASS", switch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_sol must not run when the review is skipped")

    monkeypatch.setattr(mod, "available_runner", lambda: "codex")
    monkeypatch.setattr(mod, "run_sol", fail_if_called)
    missing_brief = tmp_path / "missing-brief.md"
    argv = _argv("review", tmp_path, critic_file, "--brief-file", str(missing_brief), author=author)

    code = mod.main(argv)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "SKIPPED"
    assert [log["status"] for log in _logs(tmp_path)] == ["skipped"]


# D: atomic outcome write


def _first_run_log(tmp_path, critic_file) -> Path:
    assert _record(tmp_path, critic_file, _reply(tmp_path)) == mod.EXIT_OK
    return Path(next(_log_dir(tmp_path).glob("*.json")))


def _outcome_argv(path: Path) -> list[str]:
    return ["outcome", "--run", str(path), "--id", "S1", "--outcome", "fixed", "--evidence", "a:1"]


def test_outcome_updates_the_finding_in_the_run_log(tmp_path, critic_file, capsys):
    path = _first_run_log(tmp_path, critic_file)
    before = set(path.parent.iterdir())

    code = mod.main(_outcome_argv(path))

    finding = next(f for f in _logs(tmp_path)[0]["findings"] if f["id"] == "S1")
    assert code == mod.EXIT_OK
    assert (finding["outcome"], finding["evidence"]) == ("fixed", "a:1")
    assert set(path.parent.iterdir()) == before


def test_failed_outcome_write_keeps_the_log_and_leaves_no_temp_file(
    tmp_path, critic_file, capsys, monkeypatch
):
    path = _first_run_log(tmp_path, critic_file)
    original = path.read_bytes()
    before = sorted(path.parent.iterdir())

    def refuse(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(sys.modules["sol_ledger"].os, "replace", refuse)

    code = mod.main(_outcome_argv(path))

    assert code == mod.EXIT_CONFIG
    assert "disk full" in capsys.readouterr().err
    assert path.read_bytes() == original
    assert sorted(path.parent.iterdir()) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_replace_run_log_keeps_the_original_permission_bits(tmp_path):
    ledger = sys.modules["sol_ledger"]
    path = tmp_path / "run.json"
    path.write_text("{}\n", encoding="utf-8")
    path.chmod(0o640)

    error = ledger.replace_run_log(path, {"a": 1})

    assert error == ""
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert '"a": 1' in path.read_text(encoding="utf-8")


def test_replace_run_log_reports_a_missing_directory(tmp_path):
    ledger = sys.modules["sol_ledger"]

    error = ledger.replace_run_log(tmp_path / "gone" / "run.json", {"a": 1})

    assert error != ""
    assert not (tmp_path / "gone").exists()


# E: same-second HEAD moves


def _repo_with_head_at_2020(tmp_path: Path) -> tuple[Path, int]:
    repo = tmp_path / "repo"
    _git_repo(repo)
    _commit_file(repo, "a.py", when="2020-01-01T00:00:00Z")
    return repo, int(_git_run(repo, "log", "-1", "--format=%ct"))


@_needs_git
def test_gate_refuses_a_critic_written_in_the_same_second_as_head(tmp_path, critic_file, capsys):
    repo, head_time = _repo_with_head_at_2020(tmp_path)
    _set_mtime(critic_file, head_time + 0.5)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "older than HEAD" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_the_critic_is_a_second_past_head(tmp_path, critic_file, capsys):
    repo, head_time = _repo_with_head_at_2020(tmp_path)
    _set_mtime(critic_file, head_time + 1.5)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"
