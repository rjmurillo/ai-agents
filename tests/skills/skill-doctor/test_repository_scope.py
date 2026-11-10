"""Repository scope covers a checkout's registered worktrees and nothing guessed.

Every fixture is synthetic: directory names carry no relation to a real checkout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from repository_scope import resolve_repository_scope
from session_test_helpers import run_collector

UPSTREAM = "https://example.invalid/acme/widgets.git"
OTHER_UPSTREAM = "https://example.invalid/someone-else/widgets.git"
ROOTS = ["claude", "copilot-cli"]


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


def git_out(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=30
    ).stdout


def make_clone(path, upstream):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    git(path, "remote", "add", "origin", upstream)
    return path


def add_worktree(clone, path, branch):
    path.parent.mkdir(parents=True, exist_ok=True)
    git(clone, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def write_session(home, name, cwd, history=()):
    path = home / "session-state" / name / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    def row(kind, data):
        return {"type": kind, "timestamp": "2026-11-09T12:00:00Z", "data": data}

    rows = [
        row("session.start", {"sessionId": name, "context": {"cwd": str(cwd)}}),
        row("user.message", {"content": "Fix the parser."}),
        row(
            "assistant.message",
            {
                "content": "Reading.",
                "toolRequests": [{"toolCallId": "c1", "name": "view", "arguments": {}}],
            },
        ),
        row("tool.execution_start", {"toolCallId": "c1", "toolName": "view", "arguments": {}}),
        row("tool.execution_complete", {"toolCallId": "c1", "success": True, "result": {}}),
    ]
    rows.extend(row("session.context_changed", {"cwd": str(extra)}) for extra in history)
    path.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    """Main clone with a registered and a removed worktree, plus look-alikes."""
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    feature = add_worktree(main, tmp_path / "trees" / "widgets" / "feature-a", "feature-a")
    removed = add_worktree(main, tmp_path / "trees" / "widgets" / "gone", "gone-branch")
    shutil.rmtree(removed)
    probe = tmp_path / "trees" / "widgets" / "probe-x1y2"
    probe.mkdir(parents=True)
    (probe / "hello.txt").write_text("hello\n", encoding="utf-8")
    second_clone = make_clone(tmp_path / "clones-b" / "widgets-copy", UPSTREAM)
    same_name = make_clone(tmp_path / "elsewhere" / "widgets", OTHER_UPSTREAM)
    other_tree = add_worktree(second_clone, tmp_path / "trees-b" / "w", "other-feature")
    home = tmp_path / "home"
    places = {
        "main": main,
        "feature": feature,
        "removed": removed,
        "probe": probe,
        "second_clone": second_clone,
        "same_name": same_name,
        "other_tree": other_tree,
    }
    for name, place in places.items():
        write_session(home, name, place)
    return {"home": home, "tmp": tmp_path, **places}


def collect(world, *args, root="claude", cwd=None):
    result = run_collector(
        world["tmp"], world["home"], "--harness", "copilot", *args, root=root, cwd=cwd
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((world["tmp"] / "report" / "inventory.json").read_text(encoding="utf-8"))
    return inventory, result.stdout


def session_cwds(inventory):
    return {session["meta"]["cwd"] for session in inventory["sessions"]}


@pytest.mark.parametrize("root", ROOTS)
def test_default_scope_from_linked_worktree_covers_main_and_registered_worktrees(world, root):
    inventory, stdout = collect(world, root=root, cwd=world["feature"])

    assert session_cwds(inventory) == {str(world["main"]), str(world["feature"])}
    scope = inventory["scope_resolution"]
    included = {entry["path"]: entry for entry in scope["included"]}
    assert list(included)[0] == str(world["feature"]), "current checkout comes first"
    assert included[str(world["main"])]["kind"] == "main"
    assert included[str(world["feature"])]["sessions_considered"] == 1
    assert included[str(world["main"])]["sessions_considered"] == 1
    assert "worktrees" in stdout


@pytest.mark.parametrize("root", ROOTS)
def test_default_scope_from_main_checkout_covers_registered_worktrees(world, root):
    inventory, _ = collect(world, root=root, cwd=world["main"])

    assert session_cwds(inventory) == {str(world["main"]), str(world["feature"])}


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("selected", ["main", "feature"])
def test_explicit_repo_expands_to_the_same_repository_family(world, root, selected):
    inventory, _ = collect(world, "--repo", str(world[selected]), root=root)

    assert session_cwds(inventory) == {str(world["main"]), str(world["feature"])}


@pytest.mark.parametrize("root", ROOTS)
def test_look_alikes_never_join_the_scope(world, root):
    inventory, _ = collect(world, root=root, cwd=world["feature"])

    included = {entry["path"] for entry in inventory["scope_resolution"]["included"]}
    for name in ("probe", "second_clone", "same_name", "other_tree"):
        assert str(world[name]) not in included
        assert str(world[name]) not in session_cwds(inventory)


@pytest.mark.parametrize("root", ROOTS)
def test_removed_worktree_is_reported_and_excluded_by_default(world, root):
    inventory, _ = collect(world, root=root, cwd=world["feature"])

    rejected = {
        entry["path"]: entry["reason"] for entry in inventory["scope_resolution"]["rejected"]
    }
    assert str(world["removed"]) in rejected
    assert "missing" in rejected[str(world["removed"])]
    assert "--repo" in rejected[str(world["removed"])]
    assert str(world["removed"]) not in session_cwds(inventory)


@pytest.mark.parametrize("root", ROOTS)
def test_removed_worktree_joins_only_when_named_with_repo(world, root):
    inventory, _ = collect(
        world, "--repo", str(world["feature"]), "--repo", str(world["removed"]), root=root
    )

    assert str(world["removed"]) in session_cwds(inventory)
    included = {entry["path"]: entry for entry in inventory["scope_resolution"]["included"]}
    assert included[str(world["removed"])]["kind"] == "selected"
    rejected = {entry["path"] for entry in inventory["scope_resolution"]["rejected"]}
    assert str(world["removed"]) not in rejected


@pytest.mark.parametrize("root", ROOTS)
def test_probe_directory_under_the_worktree_parent_is_not_included(world, root):
    inventory, _ = collect(world, "--repo", str(world["main"]), root=root)

    assert str(world["probe"]) not in session_cwds(inventory)
    reported = [entry["path"] for entry in inventory["scope_resolution"]["included"]]
    assert str(world["probe"]) not in reported


@pytest.mark.parametrize("root", ROOTS)
def test_report_states_clone_discovery_is_unsupported(world, root):
    inventory, stdout = collect(world, root=root, cwd=world["feature"])

    scope = inventory["scope_resolution"]
    assert scope["clone_discovery"] == "unsupported"
    assert "clone discovery: unsupported" in stdout


@pytest.mark.parametrize("root", ROOTS)
def test_session_that_moved_between_worktrees_is_in_scope(world, root):
    write_session(world["home"], "mover", world["feature"], history=[world["main"]])

    inventory, _ = collect(world, root=root, cwd=world["feature"])

    mover = [s for s in inventory["sessions"] if s["meta"]["id"] == "mover"]
    assert len(mover) == 1
    assert mover[0]["meta"]["cwd_history"] == [str(world["feature"]), str(world["main"])]


@pytest.mark.parametrize("root", ROOTS)
def test_branch_names_do_not_filter_and_collection_leaves_branches_alone(world, root):
    before = {
        place: (
            git_out(world[place], "rev-parse", "--abbrev-ref", "HEAD"),
            git_out(world[place], "status", "--porcelain"),
            git_out(world[place], "for-each-ref"),
        )
        for place in ("main", "feature")
    }
    assert before["main"][0].strip() != before["feature"][0].strip()

    inventory, _ = collect(world, root=root, cwd=world["feature"])

    assert inventory["scope_resolution"]["branch_filter"] == "none"
    assert session_cwds(inventory) == {str(world["main"]), str(world["feature"])}
    after = {
        place: (
            git_out(world[place], "rev-parse", "--abbrev-ref", "HEAD"),
            git_out(world[place], "status", "--porcelain"),
            git_out(world[place], "for-each-ref"),
        )
        for place in ("main", "feature")
    }
    assert after == before


@pytest.mark.parametrize("root", ROOTS)
def test_selected_repository_keeps_single_repo_identity_in_inventory(world, root):
    inventory, _ = collect(world, root=root, cwd=world["feature"])

    assert inventory["repos"] == [str(world["feature"])]
    assert inventory["repo"] == str(world["feature"])
    assert inventory["repo_name"] == world["feature"].name


def test_scope_lists_current_checkout_first_then_main_then_worktrees(world):
    scope = resolve_repository_scope([world["feature"].resolve()])

    kinds = [(root.path, root.kind) for root in scope.included]
    assert kinds[0] == (world["feature"].resolve(), "selected")
    assert kinds[1] == (world["main"].resolve(), "main")
    assert len(kinds) == 2


def test_two_checkouts_of_one_family_are_listed_once(world):
    scope = resolve_repository_scope([world["main"].resolve(), world["feature"].resolve()])

    paths = [root.path for root in scope.included]
    assert len(paths) == len(set(paths)) == 2


def test_non_git_path_is_kept_as_an_explicit_selection(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    scope = resolve_repository_scope([plain.resolve()])

    assert [(root.path, root.kind) for root in scope.included] == [(plain.resolve(), "selected")]
    assert scope.rejected == []


def test_nonexistent_path_is_kept_as_an_explicit_selection(tmp_path):
    gone = tmp_path / "never-existed"

    scope = resolve_repository_scope([gone])

    assert [root.path for root in scope.included] == [gone]


def test_registration_whose_directory_points_elsewhere_is_rejected(world):
    entry = world["main"] / ".git" / "worktrees" / "feature-a"
    assert entry.is_dir()
    hijacked = world["tmp"] / "hijacked"
    hijacked.mkdir()
    (hijacked / ".git").write_text(f"gitdir: {world['tmp'] / 'nowhere'}\n", encoding="utf-8")
    (entry / "gitdir").write_text(f"{hijacked / '.git'}\n", encoding="utf-8")

    scope = resolve_repository_scope([world["main"].resolve()])

    assert hijacked.resolve() not in [root.path for root in scope.included]
    rejected = {item.path: item.reason for item in scope.rejected}
    assert "does not point back" in rejected[hijacked.resolve()]


def test_relative_gitdir_pointer_resolves_against_the_worktree(world):
    feature = world["feature"]
    gitdir = Path((feature / ".git").read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
    relative = Path("..", "..", "..", "clones", "widgets", ".git", "worktrees", gitdir.name)
    (feature / ".git").write_text(f"gitdir: {relative}\n", encoding="utf-8")

    scope = resolve_repository_scope([feature.resolve()])

    assert world["main"].resolve() in [root.path for root in scope.included]


def test_corrupt_git_pointer_degrades_to_the_selected_path(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text("not a pointer\n", encoding="utf-8")

    scope = resolve_repository_scope([broken.resolve()])

    assert [root.path for root in scope.included] == [broken.resolve()]


def test_bare_repository_lists_worktrees_without_inventing_a_main_checkout(tmp_path):
    seed = make_clone(tmp_path / "seed", UPSTREAM)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(bare)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    tree = tmp_path / "trees" / "from-bare"
    git(bare, "worktree", "add", "-q", "-b", "side", str(tree))

    scope = resolve_repository_scope([tree.resolve()])

    assert [root.path for root in scope.included] == [tree.resolve()]
    assert all(root.kind != "main" for root in scope.included)
