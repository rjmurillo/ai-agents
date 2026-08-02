"""Remote branch helpers for worktree garbage collection."""

from __future__ import annotations

from collections.abc import Callable

GitRunner = Callable[[list[str]], str]


def load_remote_head_refs(run_git: GitRunner) -> frozenset[str]:
    """Return branch names currently present on origin."""
    out = run_git(["ls-remote", "--heads", "origin"])
    heads: set[str] = set()
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        ref = parts[1]
        if ref.startswith("refs/heads/"):
            heads.add(ref.removeprefix("refs/heads/"))
    return frozenset(heads)


def load_origin_upstreams(run_git: GitRunner) -> dict[str, str]:
    """Return local branches with a configured origin upstream."""
    out = run_git(["config", "--get-regexp", r"^branch\..*\.(remote|merge)$"])
    config: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if key.startswith("branch.") and key.endswith(".remote"):
            branch = key[len("branch.") : -len(".remote")]
            config.setdefault(branch, {})["remote"] = value
        elif key.startswith("branch.") and key.endswith(".merge"):
            branch = key[len("branch.") : -len(".merge")]
            config.setdefault(branch, {})["merge"] = value

    upstreams: dict[str, str] = {}
    for branch, values in config.items():
        merge_ref = values.get("merge", "")
        if values.get("remote") == "origin" and merge_ref.startswith("refs/heads/"):
            upstreams[branch] = merge_ref.removeprefix("refs/heads/")
    return upstreams


def try_load_origin_upstreams(run_git: GitRunner) -> dict[str, str]:
    """Return origin upstreams, or an empty map when config lookup fails."""
    try:
        return load_origin_upstreams(run_git)
    except RuntimeError:
        return {}


def is_merged_by_deleted_upstream(
    branch: str,
    remote_head_refs: frozenset[str],
    origin_upstreams: dict[str, str],
) -> bool:
    """Return True when a tracked origin branch no longer exists remotely."""
    upstream = origin_upstreams.get(branch)
    return upstream is not None and upstream not in remote_head_refs
