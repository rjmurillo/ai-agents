#!/usr/bin/env python3
"""Create or update an issue when Python Tests fails on main."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime


def _failed_needs(needs_json: str) -> list[str]:
    try:
        needs = json.loads(needs_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"NEEDS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(needs, dict):
        raise ValueError("NEEDS_JSON must be an object")
    failed = []
    for name, data in needs.items():
        if isinstance(data, dict) and data.get("result") == "failure":
            failed.append(str(name))
    return failed


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def _find_existing_issue(repository: str) -> int | None:
    query = f"repo:{repository} is:issue is:open in:title Python Tests failed on main"
    result = _run_gh(["api", "search/issues", "-f", f"q={query}", "-f", "per_page=1"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "issue search failed")
    payload = json.loads(result.stdout)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    number = first.get("number")
    return int(number) if isinstance(number, int) else None


def _issue_body(env: dict[str, str], failed_jobs: list[str]) -> str:
    run_url = (
        f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    )
    sha = env.get("GITHUB_SHA", "")
    short_sha = sha[:12] if sha else "unknown"
    jobs = "\n".join(f"- {job}" for job in failed_jobs)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""## Python Tests failed on main

Python Tests failed on `main`.

Commit: `{short_sha}`
Run: {run_url}
Time: {timestamp}

Failed job(s):
{jobs}

Action required: inspect the workflow run and fix main before more branches push.
"""


def _notify(env: dict[str, str], failed_jobs: list[str]) -> None:
    repository = env["GITHUB_REPOSITORY"]
    sha = env.get("GITHUB_SHA", "")
    short_sha = sha[:12] if sha else "unknown"
    title = f"Python Tests failed on main at {short_sha}"
    body = _issue_body(env, failed_jobs)
    existing = _find_existing_issue(repository)
    if existing is None:
        result = _run_gh(
            [
                "api",
                f"repos/{repository}/issues",
                "-X",
                "POST",
                "-f",
                f"title={title}",
                "-f",
                f"body={body}",
            ]
        )
    else:
        result = _run_gh(
            [
                "api",
                f"repos/{repository}/issues/{existing}/comments",
                "-X",
                "POST",
                "-f",
                f"body={body}",
            ]
        )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "issue notification failed")


def run(env: dict[str, str]) -> int:
    failed_jobs = _failed_needs(env.get("NEEDS_JSON", "{}"))
    if not failed_jobs:
        print("No failed Python Tests jobs on main.")
        return 0
    for name in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        if not env.get(name):
            print(f"{name} is required.", file=sys.stderr)
            return 2
    try:
        _notify(env, failed_jobs)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Failed to notify Python Tests failure: {exc}", file=sys.stderr)
        return 3
    print(f"Notified Python Tests failure for {', '.join(failed_jobs)}.")
    return 0


def main() -> int:
    return run(dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
