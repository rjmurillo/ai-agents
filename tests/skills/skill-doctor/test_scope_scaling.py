"""Scope work scales with unique Git common dirs and unique cwds, not checkout count.

Every fixture is synthetic: a throwaway main repository, linked worktrees, and
journal-like session metas that reuse a few cwd values.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest
import repository_scope
import session_discovery
from repository_scope import (
    RepositoryScope,
    ScopeRoot,
    common_dir_of,
    count_sessions_by_root,
    git_dir_of,
    resolve_repository_scope,
)
from session_discovery import (
    clear_cwd_resolution_cache,
    infer_session_repos,
    session_cwd_within_repo,
)


@pytest.fixture(autouse=True)
def _fresh_cwd_cache():
    clear_cwd_resolution_cache()
    yield
    clear_cwd_resolution_cache()


def git(cwd, *args):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=30,
    )


def build_world(tmp_path: Path, worktrees: int) -> dict[str, Any]:
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    (main / "src").mkdir()
    (main / "src" / "a.txt").write_text("a", encoding="utf-8")
    git(main, "add", ".")
    git(main, "commit", "-q", "-m", "init")
    trees = []
    for index in range(worktrees):
        tree = tmp_path / f"wt-{index}"
        git(main, "worktree", "add", "-q", "-b", f"feature-{index}", str(tree))
        trees.append(tree)
    outside = tmp_path / "outside"
    outside.mkdir()
    return {"main": main, "trees": trees, "outside": outside}


def make_sessions(world: dict[str, Any], count: int) -> list[dict[str, Any]]:
    """Return ``count`` metas drawn from four unique cwd values."""
    cwds = [
        str(world["main"]),
        str(world["main"] / "src"),
        str(world["outside"]),
        str(world["trees"][0]) if world["trees"] else str(world["main"]),
    ]
    return [{"meta": {"cwd": cwds[i % len(cwds)], "cwd_history": [cwds[0]]}} for i in range(count)]


# Reference: the logic before the change, re-implemented inline without caches.
def ref_within(cwd, repo: Path) -> bool:
    if not isinstance(cwd, str) or not cwd:
        return False
    if bool(PureWindowsPath(cwd).drive) != (os.name == "nt"):
        return False
    try:
        path = Path(cwd)
        return path.is_absolute() and path.resolve().is_relative_to(repo)
    except (OSError, ValueError):
        return False


def ref_scope(repos) -> RepositoryScope:
    scope = RepositoryScope()
    for repo in repos:
        selected = Path(repo)
        git_dir = git_dir_of(selected)
        if git_dir is None:
            scope.add(ScopeRoot(selected, "selected", "explicit path with no Git metadata"))
            continue
        common = common_dir_of(git_dir)
        scope.add(ScopeRoot(selected, "selected", "checkout the run started from or was given"))
        repository_scope._admit_main(scope, common)
        for registration, worktree in repository_scope._registrations(common):
            repository_scope._admit_worktree(scope, registration, worktree)
    return scope


def snapshot(scope: RepositoryScope):
    return (
        [(r.path, r.kind, r.reason) for r in scope.included],
        [(r.path, r.reason) for r in scope.rejected],
    )


@pytest.fixture
def counters(monkeypatch):
    state = {"registrations": 0, "resolved": [], "git_runs": 0}
    real_registrations = repository_scope._registrations
    real_resolve = Path.resolve
    real_git_root = session_discovery._git_root

    def registrations(common):
        state["registrations"] += 1
        return real_registrations(common)

    def resolve(self, *args, **kwargs):
        state["resolved"].append(str(self))
        return real_resolve(self, *args, **kwargs)

    def git_root(path):
        state["git_runs"] += 1
        return real_git_root(path)

    monkeypatch.setattr(repository_scope, "_registrations", registrations)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(session_discovery, "_git_root", git_root)
    return state


def cwd_resolutions(state, sessions) -> int:
    unique = {s["meta"]["cwd"] for s in sessions}
    return sum(1 for text in state["resolved"] if text in unique)


def test_registrations_expand_once_per_common_dir_when_every_worktree_is_selected(
    tmp_path, counters
):
    world = build_world(tmp_path, 6)
    repos = [world["main"], *world["trees"], world["main"]]
    scope = resolve_repository_scope(repos)
    assert counters["registrations"] == 1
    assert {r.path for r in scope.included} >= {world["main"], *world["trees"]}
    assert scope.paths.count(world["main"]) == 1
    assert all(scope.paths.count(tree) == 1 for tree in world["trees"])


def test_each_distinct_common_dir_expands_once(tmp_path, counters):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first = build_world(tmp_path / "one", 2)
    second = build_world(tmp_path / "two", 2)
    resolve_repository_scope([first["main"], *first["trees"], second["main"], *second["trees"]])
    assert counters["registrations"] == 2


def test_scope_equals_reference_for_every_selection_order(tmp_path):
    world = build_world(tmp_path, 4)
    (world["trees"][1] / ".git").unlink()
    for tree in (world["trees"][2],):
        (tree / ".git").write_text("gitdir: /nonexistent/elsewhere\n", encoding="utf-8")
    plain = tmp_path / "plain"
    plain.mkdir()
    selections = [
        [world["main"]],
        [world["trees"][0], world["main"]],
        [*world["trees"], world["main"], plain],
        [plain, world["trees"][3]],
    ]
    for repos in selections:
        assert snapshot(resolve_repository_scope(repos)) == snapshot(ref_scope(repos))


def test_no_worktrees_never_expands(tmp_path, counters):
    world = build_world(tmp_path, 3)
    scope = resolve_repository_scope([world["main"], *world["trees"]], expand=False)
    assert counters["registrations"] == 0
    assert [r.kind for r in scope.included] == ["selected"] * 4


def test_unauthorized_sibling_with_shared_prefix_stays_out(tmp_path):
    world = build_world(tmp_path, 1)
    sibling = Path(str(world["main"]) + "-copy")
    sibling.mkdir()
    scope = resolve_repository_scope([world["main"]])
    assert not scope.matches("claude", {"cwd": str(sibling)})
    assert scope.matches("claude", {"cwd": str(world["main"] / "src")})


def test_cwd_resolution_once_per_unique_cwd_as_checkouts_grow(tmp_path, counters):
    observed = []
    for size, name in ((2, "small"), (12, "large")):
        base = tmp_path / name
        base.mkdir()
        world = build_world(base, size)
        sessions = make_sessions(world, 200)
        counters["resolved"].clear()
        clear_cwd_resolution_cache()
        scope = resolve_repository_scope([world["main"], *world["trees"]])
        for session in sessions:
            scope.matches("copilot", session["meta"])
        count_sessions_by_root(sessions, scope.paths)
        observed.append(cwd_resolutions(counters, sessions))
    unique_cwds = 4
    assert observed == [unique_cwds, unique_cwds]


def test_cwd_cache_is_cleared_between_runs_for_retargeted_symlink(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "link"
    link.symlink_to(first, target_is_directory=True)
    assert session_cwd_within_repo(str(link), first)
    link.unlink()
    link.symlink_to(second, target_is_directory=True)
    assert session_cwd_within_repo(str(link), first)  # stale by design within one run
    clear_cwd_resolution_cache()
    assert not session_cwd_within_repo(str(link), first)
    assert session_cwd_within_repo(str(link), second)


def test_cwd_matching_equals_reference_on_edge_values(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    link = tmp_path / "alias"
    link.symlink_to(repo, target_is_directory=True)
    values = [
        str(repo),
        str(repo / "sub"),
        str(repo / ".." / "repo" / "sub"),
        str(link / "sub"),
        str(tmp_path),
        str(tmp_path / "repo-other"),
        "relative/path",
        "",
        None,
        42,
        "C:\\Users\\someone\\repo",
        "bad\0nul",
    ]
    for value in values:
        for _ in range(2):  # second pass hits the cache
            assert session_cwd_within_repo(value, repo) == ref_within(value, repo), value


def test_foreign_drive_rejected_and_not_cached_as_resolved(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX-only: Windows drive is foreign here")
    assert not session_cwd_within_repo("C:\\work\\repo", tmp_path)
    assert "C:\\work\\repo" not in session_discovery._resolved_cwds


def test_rejected_root_fencing_matches_reference(tmp_path):
    world = build_world(tmp_path, 2)
    gone = world["trees"][1]
    shutil.rmtree(gone)
    repos = [world["main"], world["trees"][0]]
    scope = resolve_repository_scope(repos)
    assert [r.path for r in scope.rejected] == [gone]
    inside_gone = {"cwd": str(gone / "deep")}
    assert not scope.matches("claude", inside_gone)
    assert scope.matches("claude", {"cwd": str(world["trees"][0])})
    assert snapshot(scope) == snapshot(ref_scope(repos))


def test_infer_session_repos_runs_git_once_per_unique_cwd(tmp_path, counters):
    world = build_world(tmp_path, 2)
    sessions = make_sessions(world, 60)
    counters["git_runs"] = 0
    repos = infer_session_repos(sessions)
    assert counters["git_runs"] == 4  # one run per unique cwd; outside runs git and fails
    assert repos == [world["main"].resolve(), world["trees"][0].resolve()]


def test_infer_session_repos_skips_empty_and_missing_cwd(tmp_path, counters):
    sessions = [
        {"meta": {}},
        {"meta": {"cwd": ""}},
        {"meta": {"cwd": str(tmp_path / "nope")}},
    ]
    assert infer_session_repos(sessions) == []
    assert counters["git_runs"] == 0


def test_benchmark_reports_workload_counts_and_runtime(tmp_path, counters, capsys):
    # Limitations: synthetic fixture, one machine, one run. It reports counts and
    # wall time to show the work no longer grows with checkouts. It is not a
    # speedup claim and says nothing about real repositories.
    checkouts, session_count = 16, 400
    world = build_world(tmp_path, checkouts - 1)
    sessions = make_sessions(world, session_count)
    repos = [world["main"], *world["trees"]]
    counters["registrations"] = 0
    started = time.perf_counter()
    scope = resolve_repository_scope(repos)
    for session in sessions:
        scope.matches("copilot", session["meta"])
    count_sessions_by_root(sessions, scope.paths)
    elapsed = time.perf_counter() - started
    resolutions = cwd_resolutions(counters, sessions)
    unique = len({s["meta"]["cwd"] for s in sessions})
    print(
        f"benchmark: checkouts={checkouts} sessions={session_count} unique_cwds={unique} "
        f"registrations={counters['registrations']} cwd_resolutions={resolutions} "
        f"seconds={elapsed:.3f}"
    )
    assert counters["registrations"] == 1
    assert resolutions == unique
    assert elapsed < 2.0
    assert "benchmark:" in capsys.readouterr().out
