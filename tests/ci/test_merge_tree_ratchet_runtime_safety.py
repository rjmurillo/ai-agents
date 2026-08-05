"""Runtime isolation tests for the merge-tree ratchet."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_memory_index_count")
def test_moving_base_ref_does_not_change_pinned_merge_or_baseline(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
    base_oid = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "checkout", "-b", "pr-branch")
    (repo / "scripts/ci/ruff_count_baseline.txt").write_text(
        "100\n", encoding="utf-8"
    )
    _commit_all(repo, "raise branch baseline")

    _git(repo, "checkout", "main")
    (repo / "scripts/ci/ruff_count_baseline.txt").write_text(
        "100\n", encoding="utf-8"
    )
    _commit_all(repo, "move target baseline")
    moved_oid = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "pr-branch")
    _git(repo, "update-ref", "refs/remotes/origin/main", base_oid)

    real_merge_tree = _m._merge_tree_oid

    def move_ref_after_merge(root: Path, pinned_base: str):
        result = real_merge_tree(root, pinned_base)
        _git(root, "update-ref", "refs/remotes/origin/main", moved_oid)
        return result

    with (
        patch.object(_m, "_merge_tree_oid", side_effect=move_ref_after_merge) as merge,
        patch.object(
            _m, "_read_baseline_at_ref", wraps=_m._read_baseline_at_ref
        ) as baseline_reader,
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=50),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
    ):
        rc = _m.main(
            ["--repo-root", str(repo), "--base-ref", "refs/remotes/origin/main"]
        )

    assert rc == _m.EXIT_REGRESSION
    assert merge.call_args.args[1] == base_oid
    assert {call.args[1] for call in baseline_reader.call_args_list} == {base_oid}
    assert _git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip() == moved_oid


def test_scratch_repo_uses_resolved_git_and_preserves_platform_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nix_path = "/nix/store/example-git/bin"
    resolved_git = r"C:\Program Files\Git\cmd\git.exe"
    monkeypatch.setenv("PATH", nix_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    calls: list[list[str]] = []
    subprocess_paths: list[str] = []

    def fake_run(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        env = kwargs.get("env")
        assert isinstance(env, dict)
        path = env.get("PATH")
        assert isinstance(path, str)
        calls.append(argv)
        subprocess_paths.append(path)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with (
        patch.object(_m, "resolve_executable", return_value=resolved_git) as resolve,
        patch.object(_m.subprocess, "run", side_effect=fake_run),
    ):
        assert _m._init_scratch_repo(scratch)

    resolved_env = resolve.call_args.kwargs["env"]
    assert resolved_env["PATH"] == nix_path
    assert all(argv[0] == resolved_git for argv in calls)
    assert subprocess_paths == [nix_path] * len(calls)
    assert all("--no-verify" not in argv for argv in calls)


def test_scratch_environment_scrubs_injected_git_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'commit.gpgSign=true'")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(tmp_path / "hostile-hooks"))
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(tmp_path / "hostile-template"))
    monkeypatch.setenv("LEFTHOOK", "0")

    isolated_home = tmp_path / "isolated-home"
    env = _m._scratch_git_environment(isolated_home)

    assert env["HOME"] == str(isolated_home)
    assert env["USERPROFILE"] == str(isolated_home)
    assert env["XDG_CONFIG_HOME"] == str(isolated_home / "xdg")
    assert env["PATH"] == os.environ["PATH"]
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == str(isolated_home / "gitconfig")
    assert "GIT_CONFIG_PARAMETERS" not in env
    assert "GIT_CONFIG_COUNT" not in env
    assert "GIT_CONFIG_KEY_0" not in env
    assert "GIT_CONFIG_VALUE_0" not in env
    assert env["GIT_TEMPLATE_DIR"] == str(isolated_home / "templates")
    assert "LEFTHOOK" not in env


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_scratch_repo_ignores_hostile_home_git_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile_home = tmp_path / "hostile-home"
    hostile_home.mkdir()
    hostile_config = hostile_home / ".gitconfig"
    hostile_config.write_text(
        "[commit]\n"
        "    gpgSign = true\n"
        "[core]\n"
        f"    hooksPath = {(tmp_path / 'hostile-hooks').as_posix()}\n"
        "[init]\n"
        f"    templateDir = {(tmp_path / 'hostile-template').as_posix()}\n"
        '[filter "hostile"]\n'
        "    clean = command-that-must-not-run\n"
        "    required = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(hostile_home))
    monkeypatch.setenv("USERPROFILE", str(hostile_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile_config))

    inherited = os.environ.copy()
    git = _m.resolve_executable("git", env=inherited)
    control = subprocess.run(
        [git, "config", "--global", "--get", "commit.gpgsign"],
        capture_output=True,
        text=True,
        check=False,
        env=inherited,
    )
    assert control.stdout.strip() == "true"

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / ".gitattributes").write_text(
        "*.txt filter=hostile\n", encoding="utf-8"
    )
    (scratch / "payload.txt").write_text("safe\n", encoding="utf-8")

    assert _m._init_scratch_repo(scratch)
