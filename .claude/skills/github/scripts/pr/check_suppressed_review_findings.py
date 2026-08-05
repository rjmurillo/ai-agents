#!/usr/bin/env python3
"""Report Copilot review findings that GitHub suppressed instead of threading."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = ""
    _here = os.path.abspath(os.path.dirname(__file__))
    _ancestor = _here
    while True:
        _candidate = os.path.join(_ancestor, "lib", "github_core")
        if os.path.isdir(_candidate):
            _lib_dir = os.path.dirname(_candidate)
            break
        _parent = os.path.dirname(_ancestor)
        if _parent == _ancestor:
            break
        _ancestor = _parent
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import assert_gh_authenticated, resolve_repo_params

_SUPPRESSED_SUMMARY_RE = re.compile(
    r"(?:<summary>\s*)?Suppressed comments\s*(?:\((\d+)\)|:\s*(\d+))",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(r"^\*\*(?P<path>[^*\n]+):(?P<line>\d+)\*\*\s*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check PR review bodies for suppressed Copilot findings.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    return parser


def _flatten_pages(payload: object) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    reviews: list[dict[str, Any]] = []
    for page in pages:
        items = page if isinstance(page, list) else [page]
        for item in items:
            if isinstance(item, dict):
                reviews.append(item)
    return reviews


def fetch_reviews(owner: str, repo: str, pull_request: int) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pull_request}/reviews?per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse review payload: {exc}") from exc
    return _flatten_pages(payload)


def _section_end(lines: list[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        line = lines[index].strip()
        if line == "</details>" or _SUPPRESSED_SUMMARY_RE.search(line):
            return index
    return len(lines)


def parse_suppressed_sections(body: str) -> list[dict[str, Any]]:
    """Extract suppressed-section counts and parsed findings from one body."""
    lines = body.splitlines()
    sections: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = _SUPPRESSED_SUMMARY_RE.search(line)
        if not match:
            continue
        declared_count = int(match.group(1) or match.group(2) or 0)
        end = _section_end(lines, index)
        findings: list[dict[str, Any]] = []
        for body_index in range(index + 1, end):
            location = _LOCATION_RE.match(lines[body_index].strip())
            if not location:
                continue
            text = ""
            for text_index in range(body_index + 1, end):
                candidate = lines[text_index].strip()
                if not candidate:
                    continue
                if candidate.startswith(("* ", "- ")):
                    text = candidate[2:].strip()
                break
            findings.append(
                {
                    "path": location.group("path"),
                    "line": int(location.group("line")),
                    "text": text,
                }
            )
        sections.append(
            {
                "declared_count": declared_count,
                "parsed_count": len(findings),
                "findings": findings,
            }
        )
    return sections


def _review_author(review: dict[str, Any]) -> str:
    user = review.get("user")
    if isinstance(user, dict):
        login = user.get("login")
        if isinstance(login, str):
            return login
    return ""


def build_report(
    owner: str, repo: str, pull_request: int, reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    suppressed_reviews: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []

    for review in reviews:
        sections = parse_suppressed_sections(str(review.get("body") or ""))
        if not sections:
            continue
        review_id = review.get("id")
        review_summary = {
            "id": review_id,
            "node_id": review.get("node_id"),
            "author": _review_author(review),
            "state": review.get("state"),
            "submitted_at": review.get("submitted_at"),
            "url": review.get("html_url"),
            "declared_count": sum(s["declared_count"] for s in sections),
            "parsed_count": sum(s["parsed_count"] for s in sections),
        }
        suppressed_reviews.append(review_summary)
        for section_index, section in enumerate(sections):
            if section["declared_count"] != section["parsed_count"]:
                mismatches.append(
                    {
                        "review_id": review_id,
                        "section_index": section_index,
                        "declared_count": section["declared_count"],
                        "parsed_count": section["parsed_count"],
                    }
                )
            for finding in section["findings"]:
                enriched = {
                    **finding,
                    "review_id": review_id,
                    "review_node_id": review.get("node_id"),
                    "review_author": _review_author(review),
                    "review_submitted_at": review.get("submitted_at"),
                    "review_url": review.get("html_url"),
                }
                findings.append(enriched)

    return {
        "success": True,
        "pull_request": pull_request,
        "owner": owner,
        "repo": repo,
        "review_count": len(reviews),
        "suppressed_review_count": len(suppressed_reviews),
        "suppressed_count": sum(r["declared_count"] for r in suppressed_reviews),
        "parsed_finding_count": len(findings),
        "fetched_pages_complete": True,
        "count_mismatches": mismatches,
        "reviews": suppressed_reviews,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        reviews = fetch_reviews(owner, repo, args.pull_request)
    except RuntimeError as exc:
        print(f"Failed to fetch PR reviews: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(build_report(owner, repo, args.pull_request, reviews), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
