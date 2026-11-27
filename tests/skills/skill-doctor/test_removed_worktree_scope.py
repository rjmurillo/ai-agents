"""Sessions from removed, short-lived worktrees stay in scope by their recorded branch.

Every repository and journal is synthetic and lives under pytest's tmp_path.
"""

from __future__ import annotations

import pytest
from repository_scope import RepositoryScope, branch_names, resolve_repository_scope
from session_test_helpers import write_jsonl
from test_repository_scope import add_worktree, git, make_clone
from test_subagent_collection import UPSTREAM, codex_rollout, collect, write_claude

OTHER_UPSTREAM = "https://example.invalid/someone-else/widgets.git"


@pytest.fixture
def repo(tmp_path):
    """A main clone, a live worktree, and a sibling removed with ``git worktree remove``."""
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    add_worktree(main, tmp_path / "trees" / "widgets" / "live", "live")
    tree = add_worktree(main, tmp_path / "trees" / "widgets" / "t3-abc", "t3/abc")
    git(main, "worktree", "remove", str(tree))
    assert not tree.exists()
    return {"main": main, "tree": tree, "tmp": tmp_path, "home": tmp_path / "claude-home"}


def run(repo, *args):
    inventory, _ = collect(
        repo["tmp"], "--claude-home", str(repo["home"]), "--repo", str(repo["main"]), *args
    )
    return inventory


def threads(inventory):
    return sorted(session["thread"] for session in inventory["sessions"])


def test_unregistered_removed_worktree_keeps_parent_and_subagent(repo):
    write_claude(repo["home"], "parent", repo["tree"], branch="t3/abc")
    inventory = run(repo)
    assert threads(inventory) == ["subagent", "top_level"]
    assert {s["meta"]["git_branch"] for s in inventory["sessions"]} == {"t3/abc"}
    assert inventory["scope_resolution"]["removed_checkout_sessions"] == 2
    assert inventory["scope_resolution"]["removed_checkout_branch_rule"] == "on"
    assert {s["meta"]["scope_via"] for s in inventory["sessions"]} == {"removed_checkout_branch"}


def test_deleted_branch_drops_the_session(repo):
    git(repo["main"], "branch", "-D", "t3/abc")
    write_claude(repo["home"], "parent", repo["tree"], branch="t3/abc")
    assert run(repo)["sessions"] == []


def test_default_branch_never_admits(repo):
    write_claude(repo["home"], "parent", repo["tree"], branch="main")
    assert run(repo)["sessions"] == []


def test_branch_unknown_to_the_repository_drops_the_session(repo):
    write_claude(repo["home"], "parent", repo["tree"], branch="someone-elses-branch")
    assert run(repo)["sessions"] == []


def test_existing_directory_elsewhere_is_not_admitted_by_branch(repo):
    elsewhere = repo["tmp"] / "unrelated"
    elsewhere.mkdir()
    write_claude(repo["home"], "parent", elsewhere, branch="t3/abc")
    assert run(repo)["sessions"] == []


def test_vanished_path_inside_another_repository_is_not_admitted(repo):
    other = make_clone(repo["tmp"] / "other" / "widgets", OTHER_UPSTREAM)
    write_claude(repo["home"], "parent", other / "deleted" / "dir", branch="t3/abc")
    assert run(repo)["sessions"] == []


def test_vanished_path_inside_the_main_checkout_is_admitted(repo):
    write_claude(repo["home"], "parent", repo["main"] / "gone" / "dir", branch="t3/abc")
    assert threads(run(repo)) == ["subagent", "top_level"]


def test_relative_cwd_is_not_admitted(repo):
    write_claude(repo["home"], "parent", "relative/dir", branch="t3/abc")
    assert run(repo)["sessions"] == []


def test_no_worktrees_turns_the_branch_rule_off(repo):
    write_claude(repo["home"], "parent", repo["tree"], branch="t3/abc")
    inventory = run(repo, "--no-worktrees")
    assert inventory["sessions"] == []
    assert inventory["scope_resolution"]["removed_checkout_sessions"] == 0


def test_codex_rollout_in_removed_worktree_is_admitted_by_git_branch(repo):
    home = repo["tmp"] / "codex-home"
    day = home / "sessions" / "2026" / "10" / "01"
    git_info = {"branch": "t3/abc", "repository_url": UPSTREAM}
    rollout = codex_rollout("kept", cwd=str(repo["tree"]), git=git_info)
    write_jsonl(day / "rollout-kept.jsonl", rollout)
    write_jsonl(
        day / "rollout-main.jsonl",
        codex_rollout("dropped", cwd=str(repo["tree"]), git={"branch": "main"}),
    )
    inventory, _ = collect(
        repo["tmp"], "--codex-home", str(home), "--repo", str(repo["main"]), harness="codex"
    )
    assert [s["meta"]["id"] for s in inventory["sessions"]] == ["kept"]


def test_branch_names_read_packed_and_remote_refs_and_skip_defaults(tmp_path):
    main = make_clone(tmp_path / "widgets", UPSTREAM)
    git(main, "branch", "feature/packed")
    git(main, "branch", "trunk")
    git(main, "update-ref", "refs/remotes/origin/remote-only", "HEAD")
    git(main, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    git(main, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    git(main, "pack-refs", "--all")
    git(main, "branch", "loose-one")
    names = branch_names(main / ".git")
    assert {"feature/packed", "remote-only", "loose-one"} <= names
    assert not names & {"main", "master", "trunk", "HEAD"}


def test_matches_ignores_copilot_and_non_string_branches(repo):
    scope = resolve_repository_scope([repo["main"].resolve()])
    meta = {"cwd": str(repo["tree"]), "cwd_history": [], "git_branch": "t3/abc"}
    assert scope.matches("claude", meta)
    assert not scope.matches("copilot", meta)
    assert not scope.matches("claude", {**meta, "git_branch": ["t3/abc"]})
    assert not scope.matches("claude", {**meta, "cwd": None})
    assert not RepositoryScope().matches("claude", meta)


def test_shared_branch_name_in_an_unrelated_directory_is_not_admitted(repo):
    unrelated = repo["tmp"] / "someone-elses-trees" / "t3-abc"
    write_claude(repo["home"], "parent", unrelated, branch="t3/abc")
    assert run(repo)["sessions"] == []


def test_nested_path_in_a_removed_sibling_is_admitted(repo):
    write_claude(repo["home"], "parent", repo["tree"] / "src" / "pkg", branch="t3/abc")
    assert threads(run(repo)) == ["subagent", "top_level"]


def test_count_covers_scoreable_sessions_only(repo):
    write_claude(repo["home"], "parent", repo["tree"], branch="t3/abc", child=False)
    idle = repo["home"] / "projects" / "-repo" / "idle.jsonl"
    write_jsonl(
        idle,
        [
            {
                "sessionId": "idle",
                "cwd": str(repo["tree"]),
                "gitBranch": "t3/abc",
                "timestamp": "2026-10-01T10:00:00Z",
                "type": "user",
                "message": {"role": "user", "content": "hi"},
            }
        ],
    )
    inventory = run(repo)
    assert inventory["stats"]["sessions_in_scope"] == 2
    assert inventory["scope_resolution"]["removed_checkout_sessions"] == 1


def test_reftable_repository_reports_the_rule_unavailable(repo):
    git(repo["main"], "config", "extensions.refStorage", "reftable")
    write_claude(repo["home"], "parent", repo["tree"], branch="t3/abc")
    inventory = run(repo)
    assert inventory["sessions"] == []
    assert inventory["scope_resolution"]["removed_checkout_branch_rule"].startswith("unavailable")
