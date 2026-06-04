"""Tests for scripts/validation/run_workflow_local_test.py.

Covers the belt-and-suspenders gate: stage ordering and short-circuit,
tool/Docker gaps -> exit 3, bypass env, --no-full, and CLI exit codes. All
external commands (actionlint, gh act, docker) are mocked; no Docker required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w  # noqa: E402

WF = ".github/workflows/x.yml"


@pytest.fixture
def all_tools(monkeypatch):
    """Pretend actionlint, gh, the gh act extension, and Docker are available."""
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: True)
    monkeypatch.setattr(w, "_docker_ready", lambda: True)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)


def _ok(stage):
    return w.StageResult(stage, True)


def _fail(stage):
    return w.StageResult(stage, False, "boom")


# --- bypass / empty ------------------------------------------------------


def test_bypass_env_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setenv(w._BYPASS_ENV, "true")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.bypassed is True


def test_bypass_env_accepts_one(monkeypatch, tmp_path):
    # Matches the repo convention: boolean env flags accept "1" and "true".
    monkeypatch.setenv(w._BYPASS_ENV, "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.bypassed is True


def test_no_files_passes(all_tools, tmp_path):
    r = w.run_local_test([], tmp_path)
    assert r.exit_code == 0
    assert r.stages == []


# --- path containment (CWE-22) + workflow filtering ----------------------


def test_path_traversal_is_exit_2(all_tools, tmp_path):
    # A path that escapes repo_root must be rejected as a config error, not run.
    r = w.run_local_test(["../../etc/passwd"], tmp_path)
    assert r.exit_code == 2
    assert "escapes repository root" in r.note


def test_absolute_path_outside_repo_is_exit_2(all_tools, tmp_path):
    r = w.run_local_test(["/etc/passwd"], tmp_path)
    assert r.exit_code == 2
    assert "escapes repository root" in r.note


def test_missing_repo_root_is_exit_2(all_tools, tmp_path):
    # A direct caller passing a non-existent repo_root is a config error (2),
    # not a stage failure (1). Matches main()'s repo-root check.
    missing = tmp_path / "does" / "not" / "exist"
    r = w.run_local_test([WF], missing)
    assert r.exit_code == 2
    assert "repo root not found" in r.note


def test_non_workflow_paths_are_filtered_out(all_tools, monkeypatch, tmp_path):
    # Custom actions and unrelated YAML never run under gh act; they drop out
    # and, with nothing left to test, the run is a clean no-op.
    r = w.run_local_test(
        [".github/actions/foo/action.yml", "README.md"], tmp_path
    )
    assert r.exit_code == 0
    assert r.note == "no workflow files to test"


def test_select_workflow_files_keeps_only_workflows(tmp_path):
    selected, err = w._select_workflow_files(
        [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yaml",
            ".github/actions/build/action.yml",
            "docs/x.yml",
            "",
        ],
        tmp_path,
    )
    assert err is None
    assert selected == [
        ".github/workflows/ci.yml",
        ".github/workflows/release.yaml",
    ]


# --- tool / docker gaps --------------------------------------------------


def test_actionlint_missing_is_exit_3(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "actionlint" in r.note


def test_gh_missing_is_exit_3(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: tool == "actionlint")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "gh" in r.note


def test_gh_act_extension_missing_is_exit_3(monkeypatch, tmp_path):
    # gh is present but the act extension is not -> exit 3 before dry-run.
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "gh act extension" in r.note


def test_docker_down_is_exit_3_for_full(all_tools, monkeypatch, tmp_path):
    # Dry-run passes (no daemon needed); the full stage needs Docker -> exit 3.
    # docker is installed but the daemon is down -> "not running" note.
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "daemon is not running" in r.note


def test_docker_not_installed_is_exit_3_with_distinct_note(monkeypatch, tmp_path):
    # docker binary absent -> "not installed" note, distinct from daemon-down.
    monkeypatch.setattr(w, "_have", lambda tool: tool != "docker")
    monkeypatch.setattr(w, "_gh_act_available", lambda: True)
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "Docker is not installed" in r.note


def test_no_full_does_not_require_docker(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    r = w.run_local_test([WF], tmp_path, full=False)
    assert r.exit_code == 0


# --- stage ordering + short-circuit --------------------------------------


def test_actionlint_failure_blocks_and_skips_act(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _fail("actionlint"))
    called = {"act": False}

    def _act(f, r):
        called["act"] = True
        return _ok("gh act -n")

    monkeypatch.setattr(w, "_act_dryrun_stage", _act)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert called["act"] is False  # short-circuit before act


def test_dryrun_failure_blocks_and_skips_full(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _fail("gh act -n"))
    called = {"full": False}

    def _full(f, r):
        called["full"] = True
        return _ok("gh act (full)")

    monkeypatch.setattr(w, "_act_full_stage", _full)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert called["full"] is False


def test_full_failure_blocks(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _fail("gh act (full)"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert [s.stage for s in r.stages] == ["actionlint", "gh act -n", "gh act (full)"]


def test_all_stages_pass(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_no_full_skips_execution_stage(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    called = {"full": False}

    def _full(f, r):
        called["full"] = True
        return _ok("gh act (full)")

    monkeypatch.setattr(w, "_act_full_stage", _full)
    r = w.run_local_test([WF], tmp_path, full=False)
    assert r.exit_code == 0
    assert called["full"] is False
    assert [s.stage for s in r.stages] == ["actionlint", "gh act -n"]


# --- stage internals (subprocess mocked) ---------------------------------


def test_actionlint_stage_passes_files(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None):
        seen["cmd"] = cmd
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._actionlint_stage([WF, "y.yml"], tmp_path)
    assert res.ok is True
    assert seen["cmd"] == ["actionlint", WF, "y.yml"]


def test_act_dryrun_stage_runs_each_file_and_stops_on_failure(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd[-1])
        return (1, "", "bad") if cmd[-1] == "a.yml" else (0, "", "")

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage(["a.yml", "b.yml"], tmp_path)
    assert res.ok is False
    assert calls == ["a.yml"]  # stopped after first failure


# --- linked-worktree GIT_DIR handling (#2344) ----------------------------


def test_read_worktree_gitdir_normal_checkout_returns_none(tmp_path):
    (tmp_path / ".git").mkdir()
    assert w._read_worktree_gitdir(tmp_path) is None


def test_read_worktree_gitdir_missing_returns_none(tmp_path):
    assert w._read_worktree_gitdir(tmp_path) is None


def test_read_worktree_gitdir_absolute_pointer(tmp_path):
    gitdir = tmp_path / "main" / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert w._read_worktree_gitdir(worktree) == str(gitdir.resolve())


def test_read_worktree_gitdir_relative_pointer(tmp_path):
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(
        "gitdir: ../.git/worktrees/feat\n", encoding="utf-8"
    )
    assert w._read_worktree_gitdir(worktree) == str(gitdir.resolve())


def test_read_worktree_gitdir_malformed_returns_none(tmp_path):
    (tmp_path / ".git").write_text("garbage\n", encoding="utf-8")
    assert w._read_worktree_gitdir(tmp_path) is None


def test_act_env_sets_git_dir_for_linked_worktree(tmp_path):
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    env = w._act_env(worktree)
    assert env["GIT_DIR"] == str(gitdir.resolve())


def test_act_env_no_git_dir_for_normal_checkout(tmp_path):
    (tmp_path / ".git").mkdir()
    env = w._act_env(tmp_path)
    assert "GIT_DIR" not in env


def test_act_dryrun_stage_passes_git_dir_env(monkeypatch, tmp_path):
    """A linked worktree's GIT_DIR reaches the gh act subprocess (#2344)."""
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    seen: dict[str, dict[str, str] | None] = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["env"] = env
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage(["a.yml"], worktree)
    assert res.ok is True
    assert seen["env"] is not None
    assert seen["env"]["GIT_DIR"] == str(gitdir.resolve())


# --- CLI -----------------------------------------------------------------


def test_cli_exit_code_propagates(all_tools, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _fail("actionlint"))
    rc = w.main(["--files", WF, "--repo-root", str(tmp_path)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_json(all_tools, monkeypatch, capsys, tmp_path):
    import json

    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    rc = w.main(["--files", WF, "--repo-root", str(tmp_path), "--no-full", "--format", "json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_cli_bad_repo_root(capsys):
    rc = w.main(["--files", WF, "--repo-root", "/no/such/xyz"])
    assert rc == 2
    assert "repo root not found" in capsys.readouterr().err
