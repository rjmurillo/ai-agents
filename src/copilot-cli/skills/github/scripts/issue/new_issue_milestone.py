#!/usr/bin/env python3
"""Milestone assignment for new_issue.py (issue #6033).

``apply_milestone`` assigns a milestone to an issue new_issue.py just created.
It confirms the milestone exists with the lookup in ``set_issue_milestone.py``,
then runs ``gh issue edit --milestone``. Every failure envelope carries the
created issue number, so automation repairs the milestone instead of
re-creating the issue.

new_issue.py loads this module by path after it puts the plugin ``lib``
directory on ``sys.path``, so ``github_core`` resolves here.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

from github_core.output import write_skill_error


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


def _milestone_error(
    message: str,
    code: int,
    error_type: str,
    fmt: str,
    context: dict[str, object],
) -> int:
    """Emit a milestone failure envelope that carries the created issue number."""
    number = context["issue_number"]
    write_skill_error(
        f"Issue #{number} created but {message}",
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="new_issue.py",
        extra=context,
    )
    return code


def _check_milestone_exists(
    owner: str,
    repo: str,
    milestone: str,
    fmt: str,
    context: dict[str, object],
) -> int | None:
    """Confirm the milestone exists using set_issue_milestone.py's lookup.

    Returns:
        ``None`` when the milestone exists, otherwise the exit code to return.
    """
    try:
        titles = _lookup._get_milestone_titles(owner, repo)
    except _lookup._MilestoneTimeoutError as err:
        return _milestone_error(f"could not look up milestone: {err}", 3, "Timeout", fmt, context)
    except _lookup._MilestoneQueryError as err:
        return _milestone_error(f"could not look up milestone: {err}", 3, "ApiError", fmt, context)
    if milestone in titles:
        return None
    return _milestone_error(
        f"milestone '{milestone}' does not exist in {owner}/{repo}.",
        2,
        "NotFound",
        fmt,
        context,
    )


def apply_milestone(
    owner: str,
    repo: str,
    issue_number: int,
    url: str,
    milestone: str | None,
    fmt: str,
) -> int | None:
    """Assign a milestone to an already-created issue.

    Assignment runs after creation, as a separate ``gh issue edit`` call, so a
    missing milestone or a failed call does not lose the created issue. Every
    failure envelope carries the issue number, URL, and milestone so automation
    can repair the milestone rather than re-create the issue.

    Returns:
        ``None`` on success (or when no milestone was requested), otherwise the
        exit code to return from ``main``.
    """
    if milestone is None:
        return None

    context: dict[str, object] = {
        "issue_number": issue_number,
        "url": url,
        "milestone": milestone,
    }
    missing = _check_milestone_exists(owner, repo, milestone, fmt, context)
    if missing is not None:
        return missing

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
        return _milestone_error(
            f"milestone assignment timed out after {timeout}s", 3, "Timeout", fmt, context
        )

    if result.returncode == 0:
        return None

    error_str = result.stderr.strip() or result.stdout.strip()
    return _milestone_error(
        f"milestone assignment failed: {error_str}", 3, "ApiError", fmt, context
    )
