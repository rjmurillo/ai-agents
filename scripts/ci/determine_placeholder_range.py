#!/usr/bin/env python3
"""Determine the git range to check for placeholder identity violations.

Called by the placeholder-identity-check workflow. Outputs the range as
a single line to stdout in the form ``<base>..<head>``.

Environment variables consumed (set by the workflow via env binding):
    EVENT_NAME   - github.event_name
    PR_BASE_SHA  - github.event.pull_request.base.sha
    PR_HEAD_SHA  - github.event.pull_request.head.sha
    MG_BASE_SHA  - github.event.merge_group.base_sha
    MG_HEAD_SHA  - github.event.merge_group.head_sha
"""

from __future__ import annotations

import os
import subprocess
import sys


def _resolve_range() -> str:
    event = os.environ.get("EVENT_NAME", "")

    if event == "pull_request":
        base = os.environ["PR_BASE_SHA"]
        head = os.environ["PR_HEAD_SHA"]
    elif event == "merge_group":
        base = os.environ["MG_BASE_SHA"]
        head = os.environ["MG_HEAD_SHA"]
    else:
        # workflow_dispatch: check all commits not on main
        result = subprocess.run(
            ["git", "merge-base", "origin/main", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        base = result.stdout.strip()
        head = "HEAD"

    return f"{base}..{head}"


if __name__ == "__main__":
    try:
        print(_resolve_range())
    except (KeyError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
