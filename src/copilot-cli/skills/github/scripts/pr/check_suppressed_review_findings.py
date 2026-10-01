#!/usr/bin/env python3
"""Report Copilot review findings that GitHub suppressed instead of threading.

A finding fixed by a change that is not a commit, such as a PR description
edit, never moves the head SHA, so it stays active. Record it in a tracked
``--dispositions-file`` instead of pushing a no-op commit. The registry must
be tracked and the completion gate compares it to the trusted ref, so it takes
effect once the entry is merged to the trusted branch, not from the PR it
waives::

    {"5091206987:0": {"disposition": "addressed-by-pr-metadata",
                      "reason": "PR body now says Refs #4725"}}

The key is ``<review id>:<finding index>``, where the index is the finding's
position in that review's ``findings`` output. Dispositions never change
``active_suppressed_count``; the gate reads ``undispositioned_suppressed_count``.
"""

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
_COPILOT_REVIEWERS = {"copilot-pull-request-reviewer[bot]"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check PR review bodies for suppressed Copilot findings.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--dispositions-file",
        default=None,
        help=(
            "Tracked JSON file recording that an active or unknown finding was "
            "addressed without a new commit (for example a PR description edit). "
            "Keys are '<review id>:<finding index>'."
        ),
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


def _run_gh_api(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", "api", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh api timed out after {timeout} seconds") from exc


def fetch_reviews(owner: str, repo: str, pull_request: int) -> list[dict[str, Any]]:
    result = _run_gh_api(
        [
            f"repos/{owner}/{repo}/pulls/{pull_request}/reviews?per_page=100",
            "--paginate",
            "--slurp",
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse review payload: {exc}") from exc
    return _flatten_pages(payload)


def fetch_pr_head(owner: str, repo: str, pull_request: int) -> str:
    result = _run_gh_api([f"repos/{owner}/{repo}/pulls/{pull_request}"])
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse PR payload: {exc}") from exc
    head = payload.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str):
        raise RuntimeError("PR head sha missing from response")
    return sha


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
                    "path": location.group("path").strip(),
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


_FINDING_DISPOSITIONS = frozenset({
    "addressed-by-pr-metadata",
    "not-applicable",
    "tracked-issue",
})


def _load_finding_dispositions(dispositions_file: str | None) -> dict[str, object]:
    """Load finding dispositions through the merge-readiness registry reader.

    Canonical source: ``_load_dispositions`` in ``test_pr_merge_ready.py``
    (same directory). Its contract, quoted from that docstring: "Returns an
    empty dict when the file is absent, unreadable, or untracked." An
    untracked registry is refused because a PR could otherwise author its own
    waiver (CWE-829, CWE-284). The completion gate byte-compares a tracked
    registry against the trusted ref before any criterion runs, so a PR that
    edits it halts the gate.

    Different from canonical: keys are ``"<review id>:<finding index>"`` rather
    than check names, entries carry no ``expires`` or ``pull_requests`` (a
    review id is unique to one PR and never reused), and
    ``_FINDING_DISPOSITIONS`` is its own vocabulary. ``disposition`` and a
    non-empty ``reason`` are required, as in ``_disposition_accepts``.

    The import is lazy so this module keeps its line layout and only pays for
    the sibling script when a registry is requested.
    """
    if not dispositions_file:
        return {}
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import test_pr_merge_ready as merge_ready

    return merge_ready._load_dispositions(dispositions_file)


def _disposition_error(entry: object) -> str:
    """Return why ``entry`` cannot disposition a finding, or "" when it can."""
    if not isinstance(entry, dict):
        return "entry is not an object"
    disposition = entry.get("disposition")
    if not isinstance(disposition, str) or disposition not in _FINDING_DISPOSITIONS:
        return f"disposition must be one of {sorted(_FINDING_DISPOSITIONS)}"
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return "reason must be a non-empty string"
    return ""


def _enrich_review_findings(
    review: dict[str, Any],
    sections: list[dict[str, Any]],
    active_state: str,
    dispositions: dict[str, object],
) -> dict[str, Any]:
    """Attach review context and any accepted disposition to each finding.

    ``finding_index`` counts findings across all sections of one review, in
    document order, starting at 0. Returns the findings, the count
    mismatches, the keys seen, the keys whose entry was rejected, and how
    many accepted dispositions count, capped per section at that section's
    declared count so surplus parsed findings in one section cannot cancel
    missing findings in another (the caller ignores it for stale reviews).
    """
    review_id = review.get("id")
    commit_id = review.get("commit_id")
    author = _review_author(review)
    findings: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    rejected: list[dict[str, Any]] = []
    dispositioned = 0
    for section_index, section in enumerate(sections):
        section_dispositioned = 0
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
            key = f"{review_id}:{len(findings)}"
            seen_keys.add(key)
            entry: Any = dispositions.get(key)
            error = _disposition_error(entry) if key in dispositions else ""
            if error:
                rejected.append({"key": key, "reason": error})
            accepted = key in dispositions and not error
            if accepted:
                section_dispositioned += 1
            findings.append(
                {
                    **finding,
                    "finding_index": len(findings),
                    "review_id": review_id,
                    "review_node_id": review.get("node_id"),
                    "review_author": author,
                    "review_commit_id": commit_id if isinstance(commit_id, str) else "",
                    "review_active_state": active_state,
                    "review_submitted_at": review.get("submitted_at"),
                    "review_url": review.get("html_url"),
                    "disposition": (
                        {"disposition": entry["disposition"], "reason": entry["reason"]}
                        if accepted
                        else None
                    ),
                }
            )
        dispositioned += min(section_dispositioned, section["declared_count"])
    return {
        "findings": findings,
        "mismatches": mismatches,
        "seen_keys": seen_keys,
        "rejected": rejected,
        "dispositioned": dispositioned,
    }


def build_report(
    owner: str,
    repo: str,
    pull_request: int,
    reviews: list[dict[str, Any]],
    head_sha: str = "",
    dispositions: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Build the suppressed-findings report.

    ``active_suppressed_count`` and ``unknown_suppressed_count`` are raw
    signals and never change with dispositions. ``dispositioned_suppressed_count``
    is the number of findings in active or unknown reviews that carry an
    accepted disposition. ``undispositioned_suppressed_count`` is what the
    completion gate reads: active plus unknown declared findings, less the
    dispositioned ones. A declared finding this parser could not read has no
    key to disposition, so it stays counted.
    """
    dispositions = dispositions or {}
    suppressed_reviews: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    rejected: list[dict[str, Any]] = []
    dispositioned_count = 0
    active_suppressed_count = 0
    stale_suppressed_count = 0
    unknown_suppressed_count = 0

    for review in reviews:
        if _review_author(review) not in _COPILOT_REVIEWERS:
            continue
        sections = parse_suppressed_sections(str(review.get("body") or ""))
        if not sections:
            continue
        review_id = review.get("id")
        commit_id = review.get("commit_id")
        active_state = "unknown"
        if isinstance(commit_id, str) and head_sha:
            active_state = "active" if commit_id == head_sha else "stale"
        declared_count = sum(s["declared_count"] for s in sections)
        if active_state == "active":
            active_suppressed_count += declared_count
        elif active_state == "stale":
            stale_suppressed_count += declared_count
        else:
            unknown_suppressed_count += declared_count
        suppressed_reviews.append(
            {
                "id": review_id,
                "node_id": review.get("node_id"),
                "author": _review_author(review),
                "state": review.get("state"),
                "commit_id": commit_id if isinstance(commit_id, str) else "",
                "active_state": active_state,
                "submitted_at": review.get("submitted_at"),
                "url": review.get("html_url"),
                "declared_count": declared_count,
                "parsed_count": sum(s["parsed_count"] for s in sections),
            }
        )
        enriched = _enrich_review_findings(review, sections, active_state, dispositions)
        findings.extend(enriched["findings"])
        mismatches.extend(enriched["mismatches"])
        seen_keys |= enriched["seen_keys"]
        rejected.extend(enriched["rejected"])
        if active_state != "stale":
            dispositioned_count += enriched["dispositioned"]

    rejected.extend(
        {"key": key, "reason": "no such review finding"}
        for key in sorted(set(dispositions) - seen_keys)
    )
    open_count = active_suppressed_count + unknown_suppressed_count
    return {
        "success": True,
        "pull_request": pull_request,
        "owner": owner,
        "repo": repo,
        "head_sha": head_sha,
        "review_count": len(reviews),
        "suppressed_review_count": len(suppressed_reviews),
        "suppressed_count": sum(r["declared_count"] for r in suppressed_reviews),
        "active_suppressed_count": active_suppressed_count,
        "stale_suppressed_count": stale_suppressed_count,
        "unknown_suppressed_count": unknown_suppressed_count,
        "dispositioned_suppressed_count": dispositioned_count,
        "undispositioned_suppressed_count": max(0, open_count - dispositioned_count),
        "rejected_dispositions": rejected,
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
        head_sha = fetch_pr_head(owner, repo, args.pull_request)
    except RuntimeError as exc:
        print(f"Failed to fetch PR reviews: {exc}", file=sys.stderr)
        return 3

    print(
        json.dumps(
            build_report(
                owner,
                repo,
                args.pull_request,
                reviews,
                head_sha,
                _load_finding_dispositions(args.dispositions_file),
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
