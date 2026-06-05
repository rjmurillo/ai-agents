"""Tests for test_workflow_locally.py skill script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("test_workflow_locally")
main = _mod.main
WORKFLOW_MAP = _mod.WORKFLOW_MAP


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class TestWorkflowMap:
    def test_known_workflows(self):
        assert "pester-tests" in WORKFLOW_MAP
        assert "validate-paths" in WORKFLOW_MAP


@patch("shutil.which")
def test_act_not_found(mock_which):
    # Neither standalone `act` nor `gh` is on PATH.
    mock_which.return_value = None

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_gh_present_but_no_act_extension(mock_run, mock_which):
    # `gh` is on PATH but the `gh act` extension is not installed.
    # `gh act --version` exits non-zero → falls back to "not found" (rc=2).
    mock_which.side_effect = lambda cmd: "/usr/bin/gh" if cmd == "gh" else None
    mock_run.return_value = _completed(stderr="unknown command \"act\"\n", rc=1)

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_gh_act_extension_fallback_succeeds(mock_run, mock_which, capsys):
    # No standalone `act`, but `gh` is present AND `gh act --version` works.
    # The script must use `gh act ...` for both version probe and execution.
    def which_side(cmd):
        if cmd == "act":
            return None
        return f"/usr/bin/{cmd}"

    mock_which.side_effect = which_side

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["gh", "act"] and len(cmd) >= 3 and cmd[2] == "--version":
            return _completed(stdout="gh act version 0.2.89\n", rc=0)
        if cmd[0] == "docker" and cmd[1] == "info":
            return _completed(rc=0)
        if cmd[:2] == ["gh", "auth"]:
            return _completed(stdout="ghp_token\n", rc=0)
        if cmd[:2] == ["gh", "act"]:
            # Workflow execution via gh act
            return _completed(rc=0)
        return _completed(rc=0)

    mock_run.side_effect = fake_run

    # Use a real workflow path via dry-run to skip resolution failure
    main(["--workflow", "pester-tests", "--dry-run"])
    # We don't assert rc==0 (workflow file may not exist in mocked env),
    # but we MUST have invoked the `gh act` runtime — not `act`.
    invoked_cmds = [c[0] for c in calls]
    assert "gh" in invoked_cmds, f"Expected gh-act invocation; got {calls}"
    # And we must never have tried to invoke standalone `act` directly.
    assert not any(c and c[0] == "act" for c in calls), (
        f"Should not invoke standalone act when only gh act is available; got {calls}"
    )
    out = capsys.readouterr().out
    assert "gh act" in out, "Log output should mention gh act runtime"


@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_found(mock_run, mock_which):
    mock_which.side_effect = lambda cmd: "/usr/bin/act" if cmd == "act" else None
    mock_run.return_value = _completed(stdout="act version 0.2.0\n")

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
@patch.object(_mod, "_get_repo_root", return_value="/repo")
def test_workflow_not_found(mock_root, mock_run, mock_which):
    mock_which.return_value = "/usr/bin/act"
    mock_run.side_effect = [
        _completed(stdout="act version 0.2.0\n"),  # act --version
        _completed(rc=0),  # docker info
    ]

    rc = main(["--workflow", "nonexistent-workflow"])
    assert rc == 1


@patch("shutil.which")
@patch("subprocess.run")
@patch("os.path.exists")
@patch.object(_mod, "_get_repo_root", return_value="/repo")
def test_successful_run(mock_root, mock_exists, mock_run, mock_which, capsys):
    mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
    mock_exists.return_value = True
    mock_run.side_effect = [
        _completed(stdout="act version 0.2.0\n"),  # act --version
        _completed(rc=0),  # docker info
        _completed(stdout="ghp_secret_token\n", rc=0),  # gh auth token
        _completed(rc=0),  # act run
    ]

    rc = main([
        "--workflow",
        "pester-tests",
        "--secrets",
        '{"API_TOKEN":"user_secret_value"}',
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "API_TOKEN=<redacted>" in out
    assert "GITHUB_TOKEN=<redacted>" in out
    assert "user_secret_value" not in out
    assert "ghp_secret_token" not in out


# ---------------------------------------------------------------------------
# Worktree-aware repo root and GIT_DIR handling (#2377, #2344)
# ---------------------------------------------------------------------------


class TestGetRepoRoot:
    def test_uses_show_toplevel(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="/repo\n", rc=0)
            assert _mod._get_repo_root() == "/repo"
            assert mock_run.call_args.args[0] == [
                "git",
                "rev-parse",
                "--show-toplevel",
            ]
            assert "GIT_WORK_TREE" not in mock_run.call_args.kwargs["env"]

    def test_returns_worktree_top_not_main_checkout(self):
        """In a linked worktree, repo root is the worktree top (#2377)."""
        worktree_top = "/repo/.git/worktrees/feat/checkout"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout=worktree_top + "\n", rc=0)
            assert _mod._get_repo_root() == worktree_top

    def test_falls_back_to_parents_when_git_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="", rc=128)
            result = _mod._get_repo_root()
            # Best-effort four-parents fallback from the script location.
            expected = str(
                Path(_mod.__file__).resolve().parent.parent.parent.parent
            )
            assert result == expected


class TestWorktreeGitDir:
    def test_normal_checkout_returns_none(self, tmp_path):
        # .git is a directory: no override needed.
        (tmp_path / ".git").mkdir()
        assert _mod._read_worktree_gitdir(str(tmp_path)) is None

    def test_linked_worktree_reads_absolute_gitdir(self, tmp_path):
        gitdir = tmp_path / "main" / ".git" / "worktrees" / "feat"
        gitdir.mkdir(parents=True)
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        result = _mod._read_worktree_gitdir(str(worktree))
        assert result == str(gitdir.resolve())

    def test_linked_worktree_resolves_relative_gitdir(self, tmp_path):
        gitdir = tmp_path / ".git" / "worktrees" / "feat"
        gitdir.mkdir(parents=True)
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text(
            "gitdir: ../.git/worktrees/feat\n", encoding="utf-8"
        )
        result = _mod._read_worktree_gitdir(str(worktree))
        assert result == str(gitdir.resolve())

    def test_missing_git_returns_none(self, tmp_path):
        assert _mod._read_worktree_gitdir(str(tmp_path)) is None

    def test_malformed_pointer_returns_none(self, tmp_path):
        (tmp_path / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")
        assert _mod._read_worktree_gitdir(str(tmp_path)) is None


class TestActEnv:
    def test_sets_git_dir_for_linked_worktree(self, tmp_path):
        gitdir = tmp_path / ".git" / "worktrees" / "feat"
        gitdir.mkdir(parents=True)
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        env = _mod._act_env(str(worktree))
        assert env["GIT_DIR"] == str(gitdir.resolve())
        assert "GIT_WORK_TREE" not in env

    def test_no_git_dir_for_normal_checkout(self, tmp_path):
        (tmp_path / ".git").mkdir()
        env = _mod._act_env(str(tmp_path))
        assert "GIT_DIR" not in env

    def test_strips_inherited_git_hook_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GIT_DIR", "/wrong/git")
        monkeypatch.setenv("GIT_WORK_TREE", "/wrong/worktree")
        monkeypatch.setenv("GIT_COMMON_DIR", "/wrong/common")
        monkeypatch.setenv("GIT_INDEX_FILE", "/wrong/index")
        env = _mod._act_env(str(tmp_path))
        assert "GIT_DIR" not in env
        assert "GIT_WORK_TREE" not in env
        assert "GIT_COMMON_DIR" not in env
        assert "GIT_INDEX_FILE" not in env
