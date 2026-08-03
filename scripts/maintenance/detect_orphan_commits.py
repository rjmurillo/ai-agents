#!/usr/bin/env python3
"""Report commits pushed to a PR branch after that PR merged.

GitHub accepts a push to the head branch of a merged PR, runs no checks against
it, and tells nobody. Under a multi-agent push model that outcome is expected
rather than rare, and one verified instance already lost a hardening change
(issue #4316, PR #4274).

Detection compares two facts that only disagree when a post-merge push
happened:

- ``headRefOid`` on the merged PR, which GitHub froze at merge time. Measured
  on PR #4274: ``fdfb4ba1e9fbe38cc91603999b2e8ddd3db592af``.
- the branch's current remote tip. Measured on the same branch:
  ``145b44b948e689eee0924812c1d2931a96c62f2e``.

A plain ancestry test against ``origin/main`` cannot carry this. A squash merge
never makes the head commit an ancestor of ``main``, so every merged PR whose
branch survives would report as lost work. Comparing the two SHAs fires only on
the real case, and a deleted branch drops out because it has no tip to compare.

EXIT CODES (mirrors ``scripts/audit_orphaned_branches.py``):
  0 - no orphan commits found
  1 - orphan commits detected (warning, not a gate)
  2 - configuration or runtime error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

DEFAULT_LIMIT = 50
_GH_TIMEOUT = 60
_GIT_TIMEOUT = 30


@dataclass(frozen=True, slots=True)
class OrphanFinding:
    """A merged PR whose branch moved after the merge."""

    number: int
    branch: str
    merged_head: str
    current_tip: str
    merged_at: str
    landed_anyway: bool


def find_orphan_commits(
    merged_prs: Iterable[Mapping[str, object]],
    remote_tips: Mapping[str, str],
    is_landed: Callable[[str], bool],
) -> list[OrphanFinding]:
    """Return the merged PRs whose head branch tip moved after the merge.

    ``remote_tips`` maps branch name to current remote SHA. A branch missing
    from it was deleted, so there is nothing left to lose. ``is_landed`` answers
    whether a SHA is already reachable from the default branch; those are
    reported with ``landed_anyway`` set so a reader can deprioritise them
    instead of losing them from the report.
    """
    findings: list[OrphanFinding] = []
    for pr in merged_prs:
        branch = str(pr.get("headRefName") or "")
        merged_head = str(pr.get("headRefOid") or "")
        if not branch or not merged_head:
            continue
        current_tip = remote_tips.get(branch)
        if not current_tip or current_tip == merged_head:
            continue
        findings.append(
            OrphanFinding(
                number=int(pr.get("number") or 0),
                branch=branch,
                merged_head=merged_head,
                current_tip=current_tip,
                merged_at=str(pr.get("mergedAt") or ""),
                landed_anyway=is_landed(current_tip),
            )
        )
    return findings


def _run(args: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def fetch_merged_prs(limit: int, repo: str | None = None) -> list[dict]:
    """Return recently merged PRs with the head SHA GitHub recorded at merge."""
    args = ["gh", "pr", "list", "--state", "merged", "--limit", str(limit)]
    if repo:
        args += ["--repo", repo]
    args += ["--json", "number,headRefName,headRefOid,mergedAt"]
    result = _run(args, _GH_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def fetch_remote_tips(remote: str = "origin") -> dict[str, str]:
    """Return ``{branch: sha}`` for every head on the remote."""
    result = _run(["git", "ls-remote", "--heads", remote], _GIT_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-remote failed: {result.stderr.strip()}")
    tips: dict[str, str] = {}
    prefix = "refs/heads/"
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[1].startswith(prefix):
            continue
        tips[parts[1][len(prefix) :]] = parts[0]
    return tips


def make_is_landed(base_ref: str = "origin/main") -> Callable[[str], bool]:
    """Return a predicate for "this SHA is already reachable from base_ref".

    An object absent from the local clone cannot be proven landed, so the
    predicate answers False and the finding stays in the report.
    """

    def is_landed(sha: str) -> bool:
        present = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], _GIT_TIMEOUT)
        if present.returncode != 0:
            return False
        ancestry = _run(
            ["git", "merge-base", "--is-ancestor", sha, base_ref], _GIT_TIMEOUT
        )
        return ancestry.returncode == 0

    return is_landed


def format_report(findings: Sequence[OrphanFinding], examined: int) -> str:
    """Render a human-readable report naming the examined count (ci-scripts MUST 12)."""
    lines = [f"orphan-commits: {len(findings)} finding(s) in {examined} merged PR(s)"]
    for finding in findings:
        status = "already on main" if finding.landed_anyway else "NOT on main"
        lines.append(
            f"  PR #{finding.number} {finding.branch}: merged at {finding.merged_head} "
            f"but branch now at {finding.current_tip} ({status}); "
            f"merged {finding.merged_at}"
        )
        lines.append(
            f"    recover with: git diff {finding.merged_head} {finding.current_tip}"
        )
    return "\n".join(lines)


def format_step_summary(findings: Sequence[OrphanFinding], examined: int) -> str:
    """Render the Markdown block appended to the GitHub Actions job summary."""
    heading = f"## Orphan commits on merged PR branches ({len(findings)} in {examined})"
    if not findings:
        return f"{heading}\n\nNo merged PR branch moved after its merge.\n"
    rows = [
        heading,
        "",
        "A commit pushed to a merged PR's branch runs no checks and merges nowhere.",
        "",
        "| PR | Branch | Merged at SHA | Branch now at | On main | Recover |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        landed = "yes" if finding.landed_anyway else "**no**"
        rows.append(
            f"| #{finding.number} | `{finding.branch}` | `{finding.merged_head[:12]}` "
            f"| `{finding.current_tip[:12]}` | {landed} "
            f"| `git diff {finding.merged_head[:12]} {finding.current_tip[:12]}` |"
        )
    return "\n".join(rows) + "\n"


def write_step_summary(text: str, summary_path: str | None) -> bool:
    """Append ``text`` to the job summary file. Return True when it was written.

    The detector runs ``continue-on-error: true`` so a finding never blocks the
    hourly sweep, which means its exit code reaches nobody and its stdout is
    buried in the log of an always-green step. The job summary is the surface a
    human actually reads, and the discovery step immediately above already
    writes there through ``scripts/ci/write_pr_discovery_summary.py``
    (issue #4316).
    """
    if not summary_path:
        return False
    try:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        print(f"WARNING: could not write the job summary: {error}", file=sys.stderr)
        return False
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--repo", default=None, help="owner/name; defaults to the clone")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        merged_prs = fetch_merged_prs(args.limit, args.repo)
        remote_tips = fetch_remote_tips()
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    findings = find_orphan_commits(merged_prs, remote_tips, make_is_landed(args.base_ref))
    if args.as_json:
        print(
            json.dumps(
                {
                    "examined": len(merged_prs),
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
            )
        )
    else:
        print(format_report(findings, len(merged_prs)))
    write_step_summary(
        format_step_summary(findings, len(merged_prs)),
        os.environ.get("GITHUB_STEP_SUMMARY"),
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
