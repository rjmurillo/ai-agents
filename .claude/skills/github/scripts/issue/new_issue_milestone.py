#!/usr/bin/env python3
"""Milestone checks and assignment for new_issue.py (issue #6033).

``check_milestone`` runs before the issue exists. It confirms the milestone
with the lookup in ``set_issue_milestone.py``, so a misspelled milestone exits
2 and creates nothing; a retry after fixing the argument is safe.

``assign_milestone`` runs after creation and calls ``gh issue edit
--milestone``. Its failure envelope carries the created issue number, so
automation repairs the milestone with set_issue_milestone.py instead of
re-creating the issue.

``set_issue_milestone.py`` puts the plugin ``lib`` directory on ``sys.path``
when it loads, so this module reuses its ``write_skill_error`` rather than
repeating that bootstrap.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys


def _load_lookup():
    """Load set_issue_milestone.py from beside this script, by file path.

    Loading by path keeps a same-named module elsewhere on sys.path from
    replacing the lookup.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "set_issue_milestone.py")
    spec = importlib.util.spec_from_file_location("_new_issue_set_milestone", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load milestone lookup: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_lookup = _load_lookup()
write_skill_error = _lookup.write_skill_error


def _error(message: str, code: int, error_type: str, fmt: str, extra: dict[str, object]) -> int:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="new_issue.py",
        extra=extra,
    )
    return code


def check_milestone(owner: str, repo: str, milestone: str | None, fmt: str) -> int | None:
    """Confirm the milestone exists before the issue is created.

    Returns:
        ``None`` when the milestone exists or none was requested, otherwise the
        exit code to return from ``main``. No issue exists on any failure path.
    """
    if milestone is None:
        return None
    extra: dict[str, object] = {"milestone": milestone}
    try:
        titles = _lookup._get_milestone_titles(owner, repo)
    except _lookup._MilestoneTimeoutError as err:
        return _error(f"{err}. No issue was created.", 3, "Timeout", fmt, extra)
    except _lookup._MilestoneQueryError as err:
        return _error(f"{err}. No issue was created.", 3, "ApiError", fmt, extra)
    if milestone in titles:
        return None
    message = f"Milestone '{milestone}' does not exist in {owner}/{repo}. No issue was created."
    return _error(message, 2, "NotFound", fmt, extra)


def assign_milestone(
    owner: str,
    repo: str,
    issue_number: int,
    url: str,
    milestone: str | None,
    fmt: str,
) -> int | None:
    """Assign a checked milestone to an already-created issue.

    Every failure envelope carries the issue number, URL, and milestone so
    automation can repair the milestone rather than re-create the issue.

    Returns:
        ``None`` on success (or when no milestone was requested), otherwise the
        exit code to return from ``main``.
    """
    if milestone is None:
        return None
    extra: dict[str, object] = {"issue_number": issue_number, "url": url, "milestone": milestone}
    prefix = f"Issue #{issue_number} created but milestone assignment"
    timeout = _lookup.GH_TIMEOUT_SECONDS
    gh_args = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", f"{owner}/{repo}", "--milestone", milestone,
    ]
    try:
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _error(f"{prefix} timed out after {timeout}s", 3, "Timeout", fmt, extra)
    if result.returncode == 0:
        return None
    error_str = result.stderr.strip() or result.stdout.strip()
    return _error(f"{prefix} failed: {error_str}", 3, "ApiError", fmt, extra)
