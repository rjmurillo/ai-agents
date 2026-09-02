"""Runtime isolation tests for the merge-tree ratchet."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_materialization as _mat
from scripts.ci import merge_tree_ratchet_check as _m
from scripts.ci import type_ignore_count_ratchet as _type_ignore
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
)
from tests.test_lefthook_integration import _MINIMUM_MARGIN_SECONDS


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
def test_every_ratchet_reports_a_verdict_before_the_outer_cap_fires(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #5441: an exhausted deadline still ends with a verdict per ratchet.

    ``_evaluate_registered_ratchets`` checks the deadline before each
    ratchet's turn, not once for the whole loop, so an already-expired
    deadline (simulating the outer Lefthook timeout closing in) must still
    print a clear FAIL for every registered ratchet rather than silently
    skipping the rest or letting the caller be killed with no diagnostic.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count") as ruff_counter,
        patch("scripts.ci.taste_count_ratchet.current_count") as taste_counter,
        patch("scripts.ci.type_ignore_count_ratchet.current_count") as ignore_counter,
    ):
        rc = _m._evaluate_merged_tree(repo, "HEAD", deadline=time.monotonic() - 1)

    assert rc == _m.EXIT_EXTERNAL
    error = capsys.readouterr().err
    for ratchet in _m.RATCHETS:
        assert f"{ratchet.label}: FAIL. Not run: aggregate timeout exhausted." in error
    ruff_counter.assert_not_called()
    taste_counter.assert_not_called()
    ignore_counter.assert_not_called()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
def test_a_counter_does_not_start_on_a_budget_too_small_to_finish_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #5441 review: an unexpired deadline is not enough to start a counter.

    Checking only ``now >= deadline`` bounds when a counter starts, never how
    long it runs, so one that begins a second before the deadline still runs to
    completion and the overrun reaches Lefthook's outer cap as an opaque kill.
    Three of the five registered counters spawn no subprocess, so no timeout
    argument can carry this bound. The start decision carries it instead.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    # Unexpired, but far below _COUNTER_RESERVE_SECONDS: the old check passed.
    deadline = time.monotonic() + 1

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count") as ruff_counter,
        patch("scripts.ci.taste_count_ratchet.current_count") as taste_counter,
        patch("scripts.ci.type_ignore_count_ratchet.current_count") as ignore_counter,
    ):
        rc = _m._evaluate_merged_tree(repo, "HEAD", deadline=deadline)

    assert rc == _m.EXIT_EXTERNAL
    error = capsys.readouterr().err
    for ratchet in _m.RATCHETS:
        assert f"{ratchet.label}: FAIL. Not run: aggregate timeout exhausted." in error
    ruff_counter.assert_not_called()
    taste_counter.assert_not_called()
    ignore_counter.assert_not_called()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
def test_a_budget_that_covers_the_reserve_runs_every_counter(tmp_path: Path) -> None:
    """The reserve must not refuse a run with room: the happy path still runs."""
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    deadline = time.monotonic() + _m._COUNTER_RESERVE_SECONDS + 60

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0) as ruff,
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0) as taste,
        patch(
            "scripts.ci.type_ignore_count_ratchet.current_count", return_value=0
        ) as ignore,
    ):
        rc = _m._evaluate_merged_tree(repo, "HEAD", deadline=deadline)

    assert rc == _m.EXIT_OK
    ruff.assert_called_once()
    taste.assert_called_once()
    ignore.assert_called_once()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
def test_preparation_spends_the_same_deadline_the_counters_do(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #5441 review: the default deadline starts before preparation.

    Taking it afterwards made the job's true ceiling ``preparation +
    _TIMEOUT_SECONDS``. Preparation runs git fetch, rev-parse, and merge-tree,
    so preparation slower than the 30s outer margin pushed the total past
    Lefthook's 2m cap, which is the opaque kill the deadline exists to replace
    with a verdict.

    Modelled by a preparation that burns the whole window: if the clock starts
    before it, every counter is out of budget and reports its own FAIL. If the
    clock started after, each counter would get a fresh 90s and run.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    real_prepare = _m._prepare_merged_tree
    start = time.monotonic()

    def exhausted_clock() -> float:
        return start + _m._TIMEOUT_SECONDS + 1

    def slow_prepare(
        root: Path, base_ref: str
    ) -> tuple[str | None, str | None, int]:
        result = real_prepare(root, base_ref)
        # Burn more than _TIMEOUT_SECONDS of the caller's window without
        # sleeping: move the clock, not the wall. monkeypatch restores it.
        monkeypatch.setattr(_m.time, "monotonic", exhausted_clock)
        return result

    with (
        patch.object(_m, "_prepare_merged_tree", side_effect=slow_prepare),
        # Real values, so the old ordering fails the assertions below
        # rather than blowing up comparing a MagicMock to a baseline.
        patch(
            "scripts.ci.ruff_count_ratchet.current_count", return_value=0
        ) as ruff_counter,
        patch(
            "scripts.ci.taste_count_ratchet.current_count", return_value=0
        ) as taste_counter,
    ):
        rc = _m._evaluate_merged_tree(repo, "HEAD")

    assert rc == _m.EXIT_EXTERNAL
    error = capsys.readouterr().err
    for ratchet in _m.RATCHETS:
        assert f"{ratchet.label}: FAIL. Not run: aggregate timeout exhausted." in error
    ruff_counter.assert_not_called()
    taste_counter.assert_not_called()


def test_the_reserve_fits_inside_the_deadline_and_the_outer_margin() -> None:
    """The two claims _COUNTER_RESERVE_SECONDS' docstring makes, as assertions.

    A reserve at or above the deadline would refuse every counter outright. A
    reserve above the outer Lefthook margin would let a counter that starts at
    the last allowed moment and runs the full reserve overrun that cap.
    ``_MINIMUM_MARGIN_SECONDS`` is the margin tests/test_lefthook_integration.py
    already enforces between a job's outer timeout and its inner deadline.
    """
    assert 0 < _m._COUNTER_RESERVE_SECONDS < _m._TIMEOUT_SECONDS
    assert _m._COUNTER_RESERVE_SECONDS <= _MINIMUM_MARGIN_SECONDS


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_remote_refresh_failure_stops_before_merge_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)

    with patch.object(_m, "_merge_tree_oid") as merge_tree:
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "origin/main"])

    assert rc == _m.EXIT_EXTERNAL
    merge_tree.assert_not_called()
    assert "failed to refresh origin/main" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
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
        patch.object(_m, "_refresh_base_ref", return_value=True),
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
        patch.object(_mat, "resolve_executable", return_value=resolved_git) as resolve,
        patch.object(_mat.subprocess, "run", side_effect=fake_run),
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
    env = _mat.isolated_git_environment(isolated_home)

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
    git = _mat.resolve_executable("git", env=inherited)
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


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_linked_worktree_real_counter_sees_merged_addition_and_deletion(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=1)
    ignore_comment = "# type:" + " ignore"
    (repo / "deleted.py").write_text(
        f"x = value  {ignore_comment}\n", encoding="utf-8"
    )
    _commit_all(repo, "add type ignore that branch deletes")

    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "pr-branch", str(linked), "main")
    _git(linked, "rm", "-q", "deleted.py")
    _commit_all(linked, "delete old type ignore")
    (repo / "added.py").write_text(
        f"y = value  {ignore_comment}\n", encoding="utf-8"
    )
    _commit_all(repo, "add target-side type ignore")

    real_counter = _type_ignore.current_count

    def observe_merged_tree(root: Path) -> int | None:
        assert (root / "added.py").is_file()
        assert not (root / "deleted.py").exists()
        return real_counter(root)

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch(
            "scripts.ci.type_ignore_count_ratchet.current_count",
            side_effect=observe_merged_tree,
        ),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        rc = _m.main(["--repo-root", str(linked), "--base-ref", "main"])

    assert rc == _m.EXIT_OK
