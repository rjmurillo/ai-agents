#!/usr/bin/env python3
"""Audit closing claims across open pull requests.

For each open PR, compares closing-keyword claims in the body against
GitHub's authoritative closingIssuesReferences GraphQL field. Reports
mismatches: claims that appear in the body but are absent from the
GitHub linkage (and thus will not auto-close on merge).

Common mismatch causes:
  - Multiple issue numbers on one "Fixes #A #B" line: GitHub closes
    only the first.
  - "Refs #N": that keyword never triggers auto-close.
  - Cross-repo references like "org/repo#N".

Output is the standard skill envelope per ADR-056.

Exit codes follow ADR-035:
    0 - Audit complete (mismatches may exist; see output)
    2 - Config error (invalid params)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import assert_gh_authenticated, resolve_repo_params
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "audit_closing_claims.py"

# Closing keywords that GitHub recognises. "Refs" is NOT in this list:
# it never triggers auto-close on merge.
_CLOSING_KEYWORDS = re.compile(
    r"(?i)\b(close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+"
    r"(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+)"
)

# Any keyword that looks like it intends an issue reference, including "Refs".
_ANY_KEYWORD = re.compile(
    r"(?i)\b(close[sd]?|fix(?:es|ed)?|resolve[sd]?|refs?)\s+"
    r"(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+)"
)

# A code-span or fenced block surrounding a hash reference: not a real claim.
_CODE_SPAN = re.compile(r"`[^`]*`")
_FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_ESCAPED_HASH = re.compile(r"\\#\d+")


def _strip_code(text: str) -> str:
    """Remove fenced blocks and inline code so hashes inside them are skipped."""
    text = _FENCED_BLOCK.sub("", text)
    text = _CODE_SPAN.sub("", text)
    text = _ESCAPED_HASH.sub("", text)
    return text


def _extract_body_claims(body: str) -> list[dict]:
    """Return all issue references that carry closing intent from a PR body."""
    clean = _strip_code(body or "")
    results = []
    for m in _ANY_KEYWORD.finditer(clean):
        num = int(m.group("num"))
        repo = m.group("repo") or ""
        keyword = m.group(1).lower()
        is_closing = bool(_CLOSING_KEYWORDS.match(m.group(0)))
        results.append({
            "number": num,
            "repo": repo,
            "keyword": keyword,
            "text": m.group(0),
            "is_closing_keyword": is_closing,
        })
    return results


def _graphql_query(repo_flag: str, cursor: str | None) -> list[dict]:
    """Fetch one page of open PRs with closing refs via GraphQL."""
    after = f', after: "{cursor}"' if cursor else ""
    query = f"""
query {{
  repository(owner: "{repo_flag.split('/')[0]}", name: "{repo_flag.split('/')[1]}") {{
    pullRequests(first: 50, states: [OPEN]{after}) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        number
        title
        baseRefName
        body
        closingIssuesReferences(first: 25) {{
          nodes {{ number }}
        }}
      }}
    }}
  }}
}}
""".strip()
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"GraphQL failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    pr_data = data["data"]["repository"]["pullRequests"]
    return pr_data["nodes"], pr_data["pageInfo"]


def audit_prs(repo_flag: str) -> list[dict]:
    """Audit all open PRs and return the mismatch report."""
    cursor = None
    all_prs = []
    while True:
        nodes, page_info = _graphql_query(repo_flag, cursor)
        all_prs.extend(nodes)
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]

    report = []
    for pr in all_prs:
        num = pr["number"]
        body = pr.get("body") or ""
        linked_nums = {n["number"] for n in pr["closingIssuesReferences"]["nodes"]}
        body_claims = _extract_body_claims(body)

        mismatches = []
        for claim in body_claims:
            # Only flag same-repo or unqualified refs.
            if claim["repo"] and claim["repo"] != repo_flag:
                continue
            if claim["number"] not in linked_nums:
                mismatches.append({
                    "claimed_issue": claim["number"],
                    "keyword": claim["keyword"],
                    "is_closing_keyword": claim["is_closing_keyword"],
                    "claim_text": claim["text"],
                    "in_github_linkage": False,
                })

        report.append({
            "pr": num,
            "title": pr["title"],
            "base": pr["baseRefName"],
            "body_claims": body_claims,
            "github_closing_refs": sorted(linked_nums),
            "mismatches": mismatches,
        })
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit closing claims across open pull requests.",
    )
    parser.add_argument("--owner", help="Repository owner (default: inferred)")
    parser.add_argument("--repo", help="Repository name (default: inferred)")
    parser.add_argument(
        "--output-file",
        help="Write JSON evidence map to this path (for resumable audits).",
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    repo_flag = f"{resolved.owner}/{resolved.repo}"

    try:
        report = audit_prs(repo_flag)
    except RuntimeError as exc:
        write_skill_error(
            str(exc),
            3,
            error_type="ApiError",
            output_format=output_format,
            script_name=_SCRIPT_NAME,
        )
        return 3

    total_prs = len(report)
    total_mismatches = sum(len(r["mismatches"]) for r in report)

    if args.output_file:
        Path(args.output_file).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    write_skill_output(
        {
            "repo": repo_flag,
            "total_prs": total_prs,
            "prs_with_mismatches": sum(1 for r in report if r["mismatches"]),
            "total_mismatches": total_mismatches,
            "report": report,
        },
        output_format=output_format,
        human_summary=(
            f"Audited {total_prs} open PRs in {repo_flag}. "
            f"{total_mismatches} closing-claim mismatches found."
        ),
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
