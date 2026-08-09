#!/usr/bin/env python3
"""Changed workflow targets, including local contract dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_changed_paths import (  # noqa: E402
    ChangedPathMissingError,
    _changed_paths_since_base,
    _git_paths_z,
    _missing_path_message,
)
from checks_common import _resolve_branch_base_ref  # noqa: E402


def _deleted_paths_since_base(repo_root: Path, warn_label: str) -> list[str] | None:
    """Return deleted paths, treating renames as delete-plus-add."""
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        return None
    diff_args = ["diff", "--name-only", "-z", "--no-renames", "--diff-filter=D"]
    sources = (
        (diff_args + [f"{base_ref}...HEAD"], "git diff (base deletions)"),
        (diff_args + ["--cached", "HEAD"], "git diff (staged deletions)"),
        (diff_args, "git diff (unstaged deletions)"),
    )
    deleted: list[str] = []
    for args, action in sources:
        paths = _git_paths_z(repo_root, args, warn_label, action)
        if paths is None:
            return None
        deleted.extend(path for path in paths if path not in deleted)
    return deleted


def _workflow_yaml_targets(repo_root: Path) -> list[str] | None:
    """Return workflows affected by changed workflow or action contracts."""
    changed = _changed_paths_since_base(repo_root, "Workflow lint")
    deleted = _deleted_paths_since_base(repo_root, "Workflow lint")
    if changed is None or deleted is None:
        return None

    def is_workflow(path: str) -> bool:
        return path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))

    def is_action_metadata(path: str) -> bool:
        return path.startswith(".github/actions/") and path.endswith(
            ("/action.yml", "/action.yaml")
        )

    relevant = [path for path in changed if is_workflow(path) or is_action_metadata(path)]
    missing = [path for path in relevant if not (repo_root / path).is_file()]
    if missing:
        raise ChangedPathMissingError(_missing_path_message(repo_root, "Workflow lint", missing))

    workflow_root = repo_root / ".github" / "workflows"
    all_workflows = sorted(
        path.relative_to(repo_root).as_posix()
        for pattern in ("*.yml", "*.yaml")
        for path in workflow_root.glob(pattern)
    )
    if any(is_action_metadata(path) for path in [*relevant, *deleted]):
        return all_workflows

    targets = {path for path in relevant if is_workflow(path)}
    providers = targets | {path for path in deleted if is_workflow(path)}
    if not providers:
        return []
    for candidate in all_workflows:
        text = (repo_root / candidate).read_text(encoding="utf-8")
        if any(f"./{provider}" in text for provider in providers):
            targets.add(candidate)
    return sorted(targets)
