#!/usr/bin/env python3
"""Join check-runs to the required status checks of a base branch.

  required_check_producer_join.py --repo . --pr 123
  required_check_producer_join.py --repo . --sha <head-sha> --base main

Reads, through the shared github_core client (gh api, GET only):
  repos/<slug>/pulls/<n>                      (only with --pr)
  repos/<slug>/rulesets?includes_parents=true
  repos/<slug>/rules/branches/<base>          (effective rules, required_status_checks)
  repos/<slug>/commits/<sha>/check-runs?filter=all

Every list is paged until the API returns an empty page. The check-run read
also compares the collected count with total_count. A repeated page, a count
mismatch, or a failed page read exits 3 and names the page. Nothing is ever
reported from a partial read.

Each required context is reported as one of:
  produced-by-the-required-app, produced-by-another-app, missing

Output is JSON with an `examined` count. Exit codes: 0 every required context
is produced by its required app, 1 at least one is not (or no
required context exists), 2 configuration or bad
arguments, 3 external failure (gh failed or pagination could not complete).
This script does not read legacy branch protection, commit statuses, merge
queues, or the workflow run behind a check-run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_SLUG = "rjmurillo/ai-agents"
PRODUCED = "produced-by-the-required-app"
OTHER_APP = "produced-by-another-app"
MISSING = "missing"
PAGE_SIZE = 100


class ExternalFailureError(RuntimeError):
    """A GitHub read failed or pagination could not complete."""


def _lib_dir(repo: Path) -> Path:
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root and (Path(plugin_root) / "lib" / "github_core").is_dir():
        return Path(plugin_root) / "lib"
    return repo / ".claude" / "lib"


def make_client(repo: Path) -> Any:
    """Return the shared GhCliClient. Tests replace this function."""
    lib = _lib_dir(repo)
    if not (lib / "github_core").is_dir():
        raise FileNotFoundError(f"github_core not found under {lib}")
    sys.path.insert(0, str(lib))
    from github_core.gh_client import GhCliClient

    return GhCliClient()


def _get(client: Any, endpoint: str) -> Any:
    try:
        return client.rest_get(endpoint)
    except Exception as exc:
        raise ExternalFailureError(f"read failed for {endpoint}: {exc}") from exc


def _endpoint(base: str, page: int) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}per_page={PAGE_SIZE}&page={page}"


def _fingerprint(items: list[Any]) -> str:
    return json.dumps(items, sort_keys=True, default=str)


def paged(
    client: Any, base: str, items_key: str | None = None
) -> tuple[list[dict], int, int | None]:
    """Read every page. Return (items, pages_read, total_count or None).

    Stops only on an empty page. A page identical to the previous one means the
    server ignored the page parameter, which would loop forever, so it fails.
    """
    items: list[dict] = []
    total: int | None = None
    previous = None
    page = 1
    while True:
        endpoint = _endpoint(base, page)
        body = _get(client, endpoint)
        if items_key is None:
            batch = body
        else:
            if not isinstance(body, dict):
                raise ExternalFailureError(f"page {page} of {base} is not an object")
            batch = body.get(items_key)
            if page == 1 and isinstance(body.get("total_count"), int):
                total = body["total_count"]
        if not isinstance(batch, list):
            raise ExternalFailureError(
                f"page {page} of {base} has no list under {items_key or 'root'}"
            )
        if not batch:
            break
        fp = _fingerprint(batch)
        if fp == previous:
            raise ExternalFailureError(
                f"page {page} of {base} repeats page {page - 1}; pagination cannot complete"
            )
        previous = fp
        items.extend(x for x in batch if isinstance(x, dict))
        page += 1
    pages_read = page - 1
    if total is not None and len(items) != total:
        raise ExternalFailureError(
            f"{base}: collected {len(items)} items over {pages_read} pages but total_count is {total}"
        )
    return items, pages_read, total


def required_contexts(rules: list[dict]) -> list[dict]:
    """Flatten required_status_checks rules into {context, integration_id, ruleset_id}."""
    found: dict[tuple[str, Any], dict] = {}
    for rule in rules:
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for entry in params.get("required_status_checks") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("context"), str):
                continue
            key = (entry["context"], entry.get("integration_id"))
            found.setdefault(
                key,
                {
                    "context": entry["context"],
                    "integration_id": entry.get("integration_id"),
                    "ruleset_id": rule.get("ruleset_id"),
                },
            )
    return sorted(found.values(), key=lambda r: (r["context"], str(r["integration_id"])))


def classify(required: dict, runs: list[dict]) -> dict:
    """Classify one required context against the check-runs of the evaluated SHA."""
    named = [r for r in runs if r.get("name") == required["context"]]
    facts = [
        {
            "app_id": (r.get("app") or {}).get("id"),
            "app_slug": (r.get("app") or {}).get("slug"),
            "head_sha": r.get("head_sha"),
            "check_suite_id": (r.get("check_suite") or {}).get("id"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
        }
        for r in named
    ]
    want = required["integration_id"]
    if not named:
        state = MISSING
    elif want is None or any(f["app_id"] == want for f in facts):
        state = PRODUCED
    else:
        state = OTHER_APP
    return {**required, "state": state, "runs": facts}


def join(client: Any, slug: str, pr: int | None, sha: str | None, base: str | None) -> dict:
    pr_info: dict[str, Any] = {}
    if pr is not None:
        body = _get(client, f"repos/{slug}/pulls/{pr}")
        if not isinstance(body, dict):
            raise ExternalFailureError(f"repos/{slug}/pulls/{pr} is not an object")
        sha = (body.get("head") or {}).get("sha")
        base = base or (body.get("base") or {}).get("ref")
        pr_info = {"pr": pr}
        if not sha or not base:
            raise ExternalFailureError(f"pull request {pr} response lacks head.sha or base.ref")
    assert sha and base
    rulesets, rs_pages, _ = paged(client, f"repos/{slug}/rulesets?includes_parents=true")
    rules, rule_pages, _ = paged(client, f"repos/{slug}/rules/branches/{base}")
    runs, run_pages, run_total = paged(
        client, f"repos/{slug}/commits/{sha}/check-runs?filter=all", "check_runs"
    )
    required = [classify(r, runs) for r in required_contexts(rules)]
    counts = {PRODUCED: 0, OTHER_APP: 0, MISSING: 0}
    for row in required:
        counts[row["state"]] += 1
    return {
        **pr_info,
        "repo": slug,
        "base": base,
        "head_sha": sha,
        "rulesets": [
            {"id": r.get("id"), "name": r.get("name"), "enforcement": r.get("enforcement")}
            for r in rulesets
        ],
        "required": required,
        "summary": counts,
        "pages": {"rulesets": rs_pages, "rules": rule_pages, "check_runs": run_pages},
        "check_runs_total_count": run_total,
        "examined": len(rulesets) + len(rules) + len(runs),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--repo", default=".", help="path to the checkout (locates github_core); default ."
    )
    p.add_argument(
        "--slug", default=DEFAULT_SLUG, help=f"owner/name on GitHub; default {DEFAULT_SLUG}"
    )
    p.add_argument("--pr", type=int, help="pull request number (reads head SHA and base branch)")
    p.add_argument("--sha", help="head SHA to evaluate (requires --base)")
    p.add_argument("--base", help="base branch (required with --sha; overrides the PR base)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 2
    if (args.pr is None) == (args.sha is None):
        print(
            json.dumps({"error": "give exactly one of --pr or --sha", "examined": 0}),
            file=sys.stderr,
        )
        return 2
    if args.sha and not args.base:
        print(json.dumps({"error": "--sha requires --base", "examined": 0}), file=sys.stderr)
        return 2
    if args.slug.count("/") != 1:
        print(json.dumps({"error": "--slug must be owner/name", "examined": 0}), file=sys.stderr)
        return 2
    try:
        client = make_client(Path(args.repo))
    except (FileNotFoundError, ImportError) as exc:
        print(json.dumps({"error": str(exc), "examined": 0}), file=sys.stderr)
        return 2
    try:
        result = join(client, args.slug, args.pr, args.sha, args.base)
    except ExternalFailureError as exc:
        print(json.dumps({"error": str(exc), "examined": 0}), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    if not result["required"]:
        print(
            json.dumps({"note": "no required_status_checks rule found for the base branch"}),
            file=sys.stderr,
        )
        return 1
    return 0 if result["summary"][OTHER_APP] + result["summary"][MISSING] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
