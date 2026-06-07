#!/usr/bin/env python3
"""Analyze commit churn across a PR cohort, to evaluate instruction changes.

Codifies the methodology used to optimize AGENTS.md: select degenerate PRs (high
commit count) and a control cohort (low commit count), then classify every
commit headline deterministically (no LLM) to see where the commits go. A high
validation_protocol / review_response / ci_fix share with low progress is the
signature of process thrash that tighter always-on context is meant to reduce.

Reuse: after an instruction or rule change ships, re-run on the PRs merged since,
and compare the churn distribution against the historical baseline this tool
produced. The classification is deterministic, so the comparison is reproducible.

Modes:
    --prs 1013,955,458         Classify these specific PRs' commit histories.
    --high 60 --low 10         Pull all merged PRs, split into degenerate (>high)
                               and control (<low) cohorts, classify each.

Examples:
    python3 scripts/eval/analyze-pr-churn.py --prs 1013,1763,955
    python3 scripts/eval/analyze-pr-churn.py --high 60 --low 10 --output churn.json

Exit codes (ADR-035):
    0 success
    2 configuration error (bad arguments)
    3 external error (gh / GraphQL failure)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from importlib import import_module
from pathlib import Path

# Import the sibling helper whether run as a module or as a file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_pr_churn = import_module("_pr_churn")
classify = _pr_churn.classify
histogram = _pr_churn.histogram
thrash_fraction = _pr_churn.thrash_fraction

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_DISTRIBUTION_QUERY = """
query($owner:String!,$name:String!,$cursor:String){
  repository(owner:$owner,name:$name){
    pullRequests(first:100, after:$cursor, states:MERGED,
                 orderBy:{field:CREATED_AT, direction:DESC}){
      pageInfo{hasNextPage endCursor}
      nodes{number commits{totalCount} changedFiles}
    }
  }
}
"""

_COMMITS_QUERY = """
query($owner:String!,$name:String!,$n:Int!,$cursor:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$n){
      commits(first:100, after:$cursor){
        pageInfo{hasNextPage endCursor}
        nodes{commit{messageHeadline}}
      }
    }
  }
}
"""


def _graphql(query: str, variables: dict[str, str | int]) -> dict:
    """Run a gh GraphQL query with typed variables (no string interpolation)."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        cmd += [flag, f"{key}={value}"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"gh GraphQL failed: {exc}\n")
        raise SystemExit(3) from exc
    if proc.returncode != 0:
        sys.stderr.write(f"gh GraphQL failed: {proc.stderr}\n")
        raise SystemExit(3)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"failed to parse gh GraphQL response: {exc}\n")
        raise SystemExit(3) from exc
    if "errors" in result or result.get("data") is None:
        sys.stderr.write(f"gh GraphQL returned errors or null data: {result.get('errors')}\n")
        raise SystemExit(3)
    return result


def fetch_distribution(owner: str, name: str) -> list[dict]:
    """Return [{number, commits, changedFiles}] for every merged PR."""
    out: list[dict] = []
    cursor: str | None = None
    while True:
        variables: dict[str, str | int] = {"owner": owner, "name": name}
        if cursor:
            variables["cursor"] = cursor
        repo = _graphql(_DISTRIBUTION_QUERY, variables)["data"]["repository"]
        if repo is None:
            sys.stderr.write(f"repository not found: {owner}/{name}\n")
            raise SystemExit(3)
        block = repo["pullRequests"]
        for node in block["nodes"]:
            out.append(
                {
                    "number": node["number"],
                    "commits": node["commits"]["totalCount"],
                    "changedFiles": node["changedFiles"],
                }
            )
        if not block["pageInfo"]["hasNextPage"]:
            return out
        cursor = block["pageInfo"]["endCursor"]


def fetch_headlines(owner: str, name: str, pr: int) -> list[str]:
    """Return all commit message headlines for one PR (paginated)."""
    out: list[str] = []
    cursor: str | None = None
    while True:
        variables: dict[str, str | int] = {"owner": owner, "name": name, "n": pr}
        if cursor:
            variables["cursor"] = cursor
        repo = _graphql(_COMMITS_QUERY, variables)["data"]["repository"]
        if repo is None:
            sys.stderr.write(f"repository not found: {owner}/{name}\n")
            raise SystemExit(3)
        pull_request = repo["pullRequest"]
        if pull_request is None:
            sys.stderr.write(f"pull request not found: {owner}/{name}#{pr}\n")
            raise SystemExit(3)
        block = pull_request["commits"]
        out += [node["commit"]["messageHeadline"] for node in block["nodes"]]
        if not block["pageInfo"]["hasNextPage"]:
            return out
        cursor = block["pageInfo"]["endCursor"]


def analyze_pr(owner: str, name: str, pr: int) -> dict:
    """Fetch and classify one PR's commit churn."""
    headlines = fetch_headlines(owner, name, pr)
    counts = histogram(headlines)
    return {
        "pr": pr,
        "total": len(headlines),
        "counts": counts,
        "thrash_fraction": thrash_fraction(headlines),
        "top": sorted(counts.items(), key=lambda kv: -kv[1])[:4],
    }


def _aggregate(results: list[dict]) -> dict[str, int]:
    agg: dict[str, int] = {}
    for result in results:
        for bucket, count in result["counts"].items():
            agg[bucket] = agg.get(bucket, 0) + count
    return agg


def _print_cohort(title: str, results: list[dict]) -> None:
    print(f"\n=== {title} ({len(results)} PRs) ===")
    for r in results:
        top = " ".join(f"{k}={v}" for k, v in r["top"])
        print(f"#{r['pr']:<6} total={r['total']:<4} thrash={r['thrash_fraction']:<5} {top}")
    agg = _aggregate(results)
    total = sum(agg.values()) or 1
    print(f"-- aggregate over {title} --")
    for bucket, count in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(f"   {bucket:22} {count:5} ({round(100 * count / total)}%)")


def _parse_pr_list(raw: str) -> list[int]:
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        sys.stderr.write("--prs must be a comma-separated list of integers\n")
        raise SystemExit(2) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify commit churn across a PR cohort.")
    parser.add_argument("--owner", default="rjmurillo")
    parser.add_argument("--name", default="ai-agents")
    parser.add_argument("--prs", help="comma-separated PR numbers to classify")
    parser.add_argument("--high", type=int, help="degenerate cohort: commits > high")
    parser.add_argument("--low", type=int, help="control cohort: commits < low")
    parser.add_argument("--output", type=Path, help="write full JSON results here")
    args = parser.parse_args(argv)

    if not _NAME_RE.match(args.owner) or not _NAME_RE.match(args.name):
        sys.stderr.write("invalid --owner/--name\n")
        return 2
    if not args.prs and (args.high is None or args.low is None):
        sys.stderr.write("provide --prs, or both --high and --low\n")
        return 2
    if args.high is not None or args.low is not None:
        if args.high is None or args.low is None:
            sys.stderr.write("provide both --high and --low\n")
            return 2
        if args.high <= args.low or args.low <= 0:
            sys.stderr.write("--high and --low must be positive and non-overlapping: high > low\n")
            return 2

    payload: dict = {"owner": args.owner, "name": args.name}

    if args.prs:
        prs = _parse_pr_list(args.prs)
        results = [analyze_pr(args.owner, args.name, p) for p in prs]
        _print_cohort("requested PRs", results)
        payload["requested"] = results
    else:
        dist = fetch_distribution(args.owner, args.name)
        degenerate = sorted(
            (d for d in dist if d["commits"] > args.high), key=lambda d: -d["commits"]
        )
        control = [d for d in dist if d["commits"] < args.low]
        print(
            f"merged PRs: {len(dist)} | degenerate(>{args.high}): "
            f"{len(degenerate)} | control(<{args.low}): {len(control)}"
        )
        deg_results = [analyze_pr(args.owner, args.name, d["number"]) for d in degenerate]
        ctrl_results = [analyze_pr(args.owner, args.name, d["number"]) for d in control]
        _print_cohort(f"degenerate (>{args.high} commits)", deg_results)
        _print_cohort(f"control (<{args.low} commits)", ctrl_results)
        payload["degenerate"] = deg_results
        payload["control"] = ctrl_results
        payload["control_count"] = len(control)

    if args.output:
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
