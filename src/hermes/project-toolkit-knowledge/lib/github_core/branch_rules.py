"""Read the ruleset rules that apply to a branch, and pure extractors over them.

``fetch_branch_rules`` calls ``gh api`` once for a branch. The other functions
read that payload without I/O. This module sees ruleset rules only. Classic
branch protection is not visible through the endpoint it reads.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any
from urllib.parse import quote


def branch_rules_endpoint(owner: str, repo: str, branch: str) -> str | None:
    """Return the branch rules endpoint, or None when the branch path is unsafe.

    An empty branch, or any ``/`` separated segment that is empty, ``.`` or
    ``..``, could redirect the request to another API path (CWE-20). Other
    characters are percent-encoded, and the ``/`` separators are kept.
    """
    if not branch or any(segment in ("", ".", "..") for segment in branch.split("/")):
        return None
    return f"repos/{owner}/{repo}/rules/branches/{quote(branch, safe='/')}?per_page=100"


def fetch_branch_rules(owner: str, repo: str, branch: str) -> list[Any] | None:
    """Return the flattened ruleset rules that apply to a branch, or None.

    Returns None when the branch path is unsafe (``gh`` is not run), the API
    call fails, times out, ``gh`` cannot be started, the output is not JSON, or
    the payload is not a list.
    """
    endpoint = branch_rules_endpoint(owner, repo, branch)
    if endpoint is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "api", "--paginate", "--slurp", endpoint],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return (
        [rule for page in payload for rule in page]
        if payload and all(isinstance(page, list) for page in payload)
        else payload
    )


def required_contexts_from_rules(rules: list[Any]) -> list[str]:
    """Return the sorted required status check contexts found in ruleset rules."""
    contexts: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for check_entry in params.get("required_status_checks") or []:
            if isinstance(check_entry, dict):
                ctx = check_entry.get("context")
            else:
                ctx = None
            if ctx and isinstance(ctx, str):
                contexts.append(ctx)
    return sorted(set(contexts))


def rules_require_pull_request(rules: list[Any]) -> bool:
    """Return True when any ruleset rule has ``type == "pull_request"``.

    This sees ruleset rules only. Classic branch protection is not visible here.
    It counts rule presence, not ``required_approving_review_count``.
    """
    return any(isinstance(rule, dict) and rule.get("type") == "pull_request" for rule in rules)
