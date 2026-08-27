#!/usr/bin/env python3
"""Guard a bulk cancellation of PR workflow runs behind a recovery manifest.

Issue #4835. On 2026-08-09, 41 PR branches were updated in parallel, producing
820 queued or in-progress workflow runs. A panic rollback cancelled 818 of them
with no mapping from cancelled run to the event that would regenerate its
checks. Dozens of PRs were left showing cancelled, pending, or permanently
absent required contexts, and close/reopen recovered only some of them because
several workflows declared an explicit ``pull_request.types`` list that omitted
``reopened`` (issue #4827).

This tool refuses that operation unless every required context it would kill
has a recovery event the workflow demonstrably subscribes to. It is dry-run by
default and mutates only with ``--confirm``.

USAGE:
  # Plan from live API state, reporting blast radius, mutating nothing.
  uv run python scripts/bulk_cancel_guard.py --all-open-prs \\
      --recovery-event reopened --manifest recovery.json

  # Plan from a captured run inventory (no network).
  uv run python scripts/bulk_cancel_guard.py --runs-file runs.json \\
      --recovery-event synchronize

  # Execute, after the plan validated.
  uv run python scripts/bulk_cancel_guard.py --runs-file runs.json \\
      --recovery-event synchronize --manifest recovery.json --confirm

EXIT CODES (AGENTS.md contract):
  0 - the plan validates; with --confirm, every run was cancelled
  1 - at least one required context has no verified recovery path
  2 - configuration error (bad arguments, unreadable or malformed input)
  3 - external error (GitHub API failure, or a partial cancellation)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ci.ruleset_required_contexts import (
    BRANCH,
    REPOSITORY,
    REQUIRED_CONTEXTS,
)
from scripts.github_core.gh_client import GhCliClient
from scripts.github_core.protocol import GitHubClient
from scripts.github_core.recovery_manifest import (
    RecoveryManifest,
    WorkflowRun,
    manifest_to_dict,
    plan_recovery,
    run_from_mapping,
)
from scripts.github_core.workflow_event_subscriptions import (
    RECOVERY_EVENTS,
    load_workflow_subscriptions,
)
from scripts.github_core.workflow_runs import (
    PAGE_SIZE,
    cancel_runs,
    collect_runs_for_branches,
)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# Open PRs on this repository sit in the low hundreds; 50 pages of 100 is an
# order of magnitude of headroom and bounds a paging bug against a live API.
_MAX_LIST_PAGES = 50

_DEFAULT_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the guard CLI."""
    parser = argparse.ArgumentParser(
        prog="bulk_cancel_guard.py",
        description=(
            "Plan and (with --confirm) execute a bulk cancellation of PR "
            "workflow runs, refusing any batch whose required contexts have no "
            "verified recovery event."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--runs-file",
        type=Path,
        help="JSON file holding a captured run inventory; no network reads.",
    )
    source.add_argument(
        "--all-open-prs",
        action="store_true",
        help="Enumerate active runs for every open pull request.",
    )
    source.add_argument(
        "--pr",
        type=int,
        action="append",
        dest="pr_numbers",
        help="Enumerate active runs for this pull request. Repeatable.",
    )
    parser.add_argument(
        "--recovery-event",
        choices=sorted(RECOVERY_EVENTS),
        default=None,
        help=(
            "Event that will regenerate cancelled required contexts. Omitting "
            "it blocks every run that publishes a required context."
        ),
    )
    parser.add_argument(
        "--repository", default=REPOSITORY, help=f"owner/repo (default: {REPOSITORY})."
    )
    parser.add_argument(
        "--branch",
        default=BRANCH,
        help=f"Protected branch whose required contexts apply (default: {BRANCH}).",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=_DEFAULT_WORKFLOWS_DIR,
        help="Directory of workflow files used to verify event subscriptions.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Write the recovery manifest JSON to this path.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually cancel the runs. Without it nothing is mutated.",
    )
    return parser


def load_runs_file(path: Path) -> list[WorkflowRun]:
    """Read a captured run inventory from disk.

    Raises:
        ValueError: on unreadable, non-JSON, or structurally wrong input. The
            caller converts this to exit code 2 rather than proceeding with a
            partially-parsed inventory, because a dropped run record reads as
            "nothing required here" and would be cancelled unguarded.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    records = payload.get("runs") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"{path} must hold a JSON list of run records")
    return [run_from_mapping(record) for record in records]


def _open_pull_requests(
    client: GitHubClient, repository: str, base: str
) -> dict[str, int]:
    """Map head branch to PR number for every open PR targeting ``base``."""
    endpoint = f"repos/{repository}/pulls?state=open&base={base}"
    branches: dict[str, int] = {}
    for payload in iter_paginated_list(client, endpoint):
        number = payload.get("number")
        head = payload.get("head")
        ref = head.get("ref") if isinstance(head, dict) else None
        if isinstance(number, int) and isinstance(ref, str) and ref:
            branches[ref] = number
    return branches


def iter_paginated_list(client: GitHubClient, endpoint: str) -> list[dict[str, Any]]:
    """Page a REST endpoint whose body is a bare JSON array.

    The Actions endpoints wrap their items in an object, so
    :func:`~scripts.github_core.workflow_runs.iter_paginated` reads a key. The
    pulls endpoint returns a top-level array instead, which needs this second
    walk. Both stop on the first short page.
    """
    separator = "&" if "?" in endpoint else "?"
    items: list[dict[str, Any]] = []
    for page in range(1, _MAX_LIST_PAGES + 1):
        body: Any = client.rest_get(f"{endpoint}{separator}per_page={PAGE_SIZE}&page={page}")
        if not isinstance(body, list) or not body:
            return items
        items.extend(entry for entry in body if isinstance(entry, dict))
        if len(body) < PAGE_SIZE:
            return items
    return items


def _pr_branches(
    client: GitHubClient, repository: str, pr_numbers: Sequence[int]
) -> dict[str, int]:
    branches: dict[str, int] = {}
    for number in pr_numbers:
        payload = client.rest_get(f"repos/{repository}/pulls/{number}")
        head = payload.get("head")
        ref = head.get("ref") if isinstance(head, dict) else None
        if not isinstance(ref, str) or not ref:
            raise ValueError(f"pull request #{number} has no head branch")
        branches[ref] = number
    return branches


def gather_runs(args: argparse.Namespace, client: GitHubClient) -> list[WorkflowRun]:
    """Resolve the run inventory from whichever source the operator chose."""
    if args.runs_file is not None:
        return load_runs_file(args.runs_file)

    branches = (
        _open_pull_requests(client, args.repository, args.branch)
        if args.all_open_prs
        else _pr_branches(client, args.repository, args.pr_numbers or [])
    )
    return collect_runs_for_branches(client, args.repository, branches)


def format_report(manifest: RecoveryManifest) -> str:
    """Render the blast radius and any blocking reasons as text."""
    radius = manifest.blast_radius
    lines = [
        f"bulk cancel guard: {manifest.repository}",
        f"  recovery event      : {manifest.recovery_event or '(none named)'}",
        f"  workflow runs       : {radius.run_count}",
        f"  pull requests       : {radius.pr_count}",
        f"  branches            : {radius.branch_count}",
        f"  distinct workflows  : {radius.workflow_count}",
        f"  queued runs         : {radius.queued_runs}",
        f"  in-progress runs    : {radius.in_progress_runs} (occupying runners)",
        f"  required contexts   : {radius.required_context_count}",
    ]
    blocked = manifest.blocked
    if blocked:
        lines.append(f"  blocked runs        : {len(blocked)}")
        for entry in blocked[:20]:
            lines.append(
                f"    [BLOCKED] run {entry.run_id} PR #{entry.pr_number} "
                f"{entry.workflow_name}: {entry.blocked_reason}"
            )
        if len(blocked) > 20:
            lines.append(f"    ... and {len(blocked) - 20} more blocked runs")
    return "\n".join(lines)


def write_manifest(path: Path, manifest: RecoveryManifest) -> None:
    """Serialize the manifest to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest_to_dict(manifest), indent=2) + "\n", encoding="utf-8"
    )


def _execute(
    client: GitHubClient, manifest: RecoveryManifest, repository: str
) -> int:
    run_ids = [entry.run_id for entry in manifest.entries]
    outcome = cancel_runs(client, repository, run_ids)
    print(f"cancelled {len(outcome.cancelled)} of {len(run_ids)} runs")
    if outcome.is_complete:
        return EXIT_OK
    for run_id, message in outcome.failed:
        print(f"  [FAIL] run {run_id}: {message}")
    print(
        f"partial cancellation: {len(outcome.failed)} runs still active. "
        "Re-run with the same manifest to retry them."
    )
    return EXIT_EXTERNAL


def main(argv: Sequence[str] | None = None, client: GitHubClient | None = None) -> int:
    """Entry point. See the module docstring for the exit-code contract."""
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    if client is None:
        client = GhCliClient()

    try:
        runs = gather_runs(args, client)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (RuntimeError, OSError) as exc:
        print(f"[FAIL] GitHub API read failed: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    subscriptions = load_workflow_subscriptions(args.workflows_dir)
    manifest = plan_recovery(
        runs,
        required=REQUIRED_CONTEXTS,
        subscriptions=subscriptions,
        recovery_event=args.recovery_event,
        repository=args.repository,
    )

    print(format_report(manifest))

    if args.manifest is not None:
        try:
            write_manifest(args.manifest, manifest)
        except OSError as exc:
            print(f"[FAIL] cannot write manifest: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"recovery manifest written to {args.manifest}")

    if not manifest.is_safe:
        print(
            f"[FAIL] refusing to cancel: {len(manifest.blocked)} runs publish "
            "required contexts with no verified recovery path.",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

    if not args.confirm:
        print(
            f"[PASS] dry run: {manifest.blast_radius.run_count} runs are "
            "recoverable. Re-run with --confirm to cancel them."
        )
        return EXIT_OK

    return _execute(client, manifest, args.repository)


if __name__ == "__main__":
    sys.exit(main())
