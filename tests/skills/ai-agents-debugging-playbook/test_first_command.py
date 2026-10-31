"""Tests for the ai-agents-debugging-playbook first_command.py script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-debugging-playbook/scripts/first_command.py"

spec = importlib.util.spec_from_file_location("first_command", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-b", "main")
    (r / "a.txt").write_text("a")
    git(r, "add", "a.txt")
    git(r, "commit", "-m", "init")
    return r


def make_stash(repo: Path, branch: str) -> None:
    git(repo, "checkout", "-b", branch)
    (repo / "a.txt").write_text(branch)
    git(repo, "stash", "push", "-m", f"wip {branch}")


def test_stash_own_entry_is_not_foreign(repo, capsys):
    make_stash(repo, "mine")
    assert mod.main(["--repo", str(repo), "stash"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["examined"] == 1 and out["stashes"][0]["status"] == "own"


def test_stash_foreign_entry_exits_1(repo, capsys):
    make_stash(repo, "gone")
    git(repo, "checkout", "main")
    git(repo, "branch", "-D", "gone")
    assert mod.main(["--repo", str(repo), "stash"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["foreign"] == ["stash@{0}"]


def test_stash_branch_in_other_worktree_is_own(repo, tmp_path, capsys):
    make_stash(repo, "other")
    git(repo, "checkout", "main")
    git(repo, "worktree", "add", str(tmp_path / "wt"), "other")
    assert mod.main(["--repo", str(repo), "stash"]) == 0
    assert json.loads(capsys.readouterr().out)["stashes"][0]["status"] == "own"


def test_stash_empty_list(repo, capsys):
    assert mod.main(["--repo", str(repo), "stash"]) == 0
    assert json.loads(capsys.readouterr().out)["examined"] == 0


def test_stash_unparseable_subject_is_unknown(monkeypatch, repo, capsys):
    real = mod._git

    def fake(r, *args):
        return "stash@{0}\tcustom subject\n" if args[0] == "stash" else real(r, *args)

    monkeypatch.setattr(mod, "_git", fake)
    assert mod.main(["--repo", str(repo), "stash"]) == 0
    assert json.loads(capsys.readouterr().out)["stashes"][0]["status"] == "unknown"


def test_lag_counts_left_and_right(repo, capsys):
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / "b.txt").write_text("b")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-m", "ahead")
    assert mod.main(["--repo", str(repo), "lag"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["left"], out["right"], out["examined"]) == (0, 1, 1)


def test_lag_behind_exits_1(repo, capsys):
    (repo / "b.txt").write_text("b")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-m", "newer")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "reset", "--hard", "HEAD~1")
    assert mod.main(["--repo", str(repo), "lag"]) == 1
    assert json.loads(capsys.readouterr().out)["left"] == 1


def test_lag_missing_base_exits_3(repo):
    assert mod.main(["--repo", str(repo), "lag"]) == 3


def test_not_a_git_repo_exits_3(tmp_path):
    assert mod.main(["--repo", str(tmp_path), "stash"]) == 3


def test_missing_directory_exits_2(tmp_path):
    assert mod.main(["--repo", str(tmp_path / "nope"), "stash"]) == 2


def test_help_exits_0():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "stash" in r.stdout
