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

  # Retry after a partial cancellation: the manifest is itself a valid
  # --runs-file, so the file the previous run wrote is the input to this one.
  uv run python scripts/bulk_cancel_guard.py --runs-file recovery.json \\
      --recovery-event synchronize --confirm

EXIT CODES (AGENTS.md contract):
  0 - the plan validates; with --confirm, every run was cancelled
  1 - at least one required context has no verified recovery path
  2 - configuration error (bad arguments, unreadable or malformed input)
  3 - external error (GitHub API failure, or a partial cancellation)
  4 - authentication error (gh has no usable credentials)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ci.ruleset_required_contexts import (
    BRANCH,
    REPOSITORY,
    REQUIRED_CONTEXTS,
)
from scripts.github_core.gh_client import GhCliClient
from scripts.github_core.protocol import GitHubClient
from scripts.github_core.pull_request_targets import (
    open_pull_request_targets,
    pull_request_targets,
)
from scripts.github_core.recovery_manifest import (
    RecoveryManifest,
    WorkflowRun,
    manifest_to_dict,
    plan_recovery,
)
from scripts.github_core.runs_file import load_runs_file
from scripts.github_core.workflow_event_subscriptions import (
    RECOVERY_EVENTS,
    WorkflowSubscriptions,
    load_workflow_subscriptions,
)
from scripts.github_core.workflow_provenance import resolve_run_subscriptions
from scripts.github_core.workflow_runs import cancel_runs, collect_runs_for_targets

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

_DEFAULT_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Issue #4835 acceptance criteria: "Emit a recovery manifest that can
# regenerate each cancelled context" is a hard requirement, not an opt-in.
# --confirm without --manifest previously cancelled required-context runs
# with no manifest written anywhere, leaving no durable record to replay if
# the runs needed to be re-triggered. This path is the fallback destination
# so a confirmed cancellation always leaves one, matching the repo-relative
# scratch convention documented in .claude/rules/ci-scripts.md and used by
# scripts/ci/artifact_collect.py.
_DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / ".agents" / "scratch" / "bulk-cancel-recovery.json"
)


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
        help=(
            "JSON file holding a captured run inventory, or a recovery "
            "manifest this tool wrote; no network reads."
        ),
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
        "--repository",
        default=REPOSITORY,
        help=(
            f"owner/repo (default and only accepted value: {REPOSITORY}). The "
            "required-context contract is pinned; see pinned_contract_error."
        ),
    )
    parser.add_argument(
        "--branch",
        default=BRANCH,
        help=(
            "Protected branch whose required contexts apply (default and only "
            f"accepted value: {BRANCH})."
        ),
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
        help=(
            "Write the recovery manifest JSON to this path. When omitted "
            f"and --confirm is set, defaults to {_DEFAULT_MANIFEST_PATH} so "
            "a confirmed cancellation always leaves a durable manifest."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually cancel the runs. Without it nothing is mutated.",
    )
    return parser


def gather_runs(args: argparse.Namespace, client: GitHubClient) -> list[WorkflowRun]:
    """Resolve the run inventory from whichever source the operator chose."""
    if args.runs_file is not None:
        return load_runs_file(args.runs_file)

    targets = (
        open_pull_request_targets(client, args.repository, args.branch)
        if args.all_open_prs
        else pull_request_targets(client, args.repository, args.pr_numbers or [])
    )
    return collect_runs_for_targets(client, args.repository, targets)


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


def resolve_manifest_path(args: argparse.Namespace) -> Path | None:
    """Decide where to write the recovery manifest, if anywhere.

    An explicit ``--manifest`` always wins. Absent one, ``--confirm`` still
    MUST leave a durable manifest behind: cancelling required-context runs
    with zero record of what was cancelled is the exact incident this guard
    exists to prevent (issue #4835). A dry run with no ``--manifest`` keeps
    writing nothing, since a plan that mutates nothing needs no recovery
    record.
    """
    manifest: Path | None = args.manifest
    if manifest is not None:
        return manifest
    if args.confirm:
        return _DEFAULT_MANIFEST_PATH
    return None


def write_manifest(path: Path, manifest: RecoveryManifest) -> None:
    """Serialize the manifest to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest_to_dict(manifest), indent=2) + "\n", encoding="utf-8"
    )


def _execute(
    client: GitHubClient,
    manifest: RecoveryManifest,
    repository: str,
    manifest_path: Path,
) -> int:
    """Cancel every planned run, naming a retry path that actually parses.

    The retry instruction names ``--runs-file <manifest>`` rather than "the same
    manifest", and ``load_runs_file`` accepts a manifest for exactly this
    reason: the earlier wording pointed at a write-only file whose JSON shape
    ``--runs-file`` rejected, so an operator following it mid-incident got exit
    2 instead of a retry.
    """
    run_ids = [entry.run_id for entry in manifest.entries]
    outcome = cancel_runs(client, repository, run_ids)
    print(f"cancelled {len(outcome.cancelled)} of {len(run_ids)} runs")
    if outcome.is_complete:
        return EXIT_OK
    for run_id, message in outcome.failed:
        print(f"  [FAIL] run {run_id}: {message}")
    print(
        f"partial cancellation: {len(outcome.failed)} runs still active. "
        f"Retry with --runs-file {manifest_path} --confirm "
        "(cancelling an already-cancelled run is a no-op)."
    )
    return EXIT_EXTERNAL


def pinned_contract_error(args: argparse.Namespace) -> str | None:
    """Refuse a target the pinned required-context contract does not describe.

    ``REQUIRED_CONTEXTS`` is the ruleset contract for ``rjmurillo/ai-agents``
    ``main`` and nothing else, and every classification in ``_classify`` is
    scored against it. Pointed at another repository or another protected
    branch, the guard would score that target's runs against the wrong required
    set: a context the real target requires and this contract does not is
    classified as optional, and an optional run is cancelled with no recovery
    event at all.

    Constraining the options is the fail-closed half of the choice the reviewer
    offered. Loading the target's own contract is the other half, and it needs a
    live rulesets read plus a policy for what to do when that read fails, which
    is a larger change than this review pass. Refusing is correct in the
    meantime, because the alternative is planning a destructive batch against a
    contract that does not describe the target.
    """
    if args.repository == REPOSITORY and args.branch == BRANCH:
        return None
    return (
        f"required-context contract is pinned to {REPOSITORY} {BRANCH} "
        f"(scripts/ci/ruleset_required_contexts.py), but --repository is "
        f"{args.repository!r} and --branch is {args.branch!r}. Planning against "
        "a target this contract does not describe would classify that target's "
        "required checks as optional and cancel them with no recovery event."
    )


def _authenticated(client: GitHubClient) -> bool:
    """Whether ``gh`` holds usable credentials, treating a probe error as no."""
    try:
        return client.is_authenticated()
    except (RuntimeError, OSError, ValueError):
        return False


def _needs_credentials(args: argparse.Namespace) -> bool:
    """Whether this invocation will read from or write to the live API.

    A ``--runs-file`` dry run touches nothing and needs no credentials, which
    keeps the offline replay path usable on a machine with no ``gh`` login.
    ``--confirm`` always needs them, because cancelling is a live write however
    the inventory was sourced.
    """
    return args.runs_file is None or args.confirm


def _resolve_live_subscriptions(
    args: argparse.Namespace,
    client: GitHubClient,
    runs: Sequence[WorkflowRun],
    subscriptions: Mapping[str, WorkflowSubscriptions],
) -> dict[int, WorkflowSubscriptions | None] | None:
    """Pin each live-enumerated run to its own pull request's definition.

    Returns None on the ``--runs-file`` path, where there is no network read to
    make and the local corpus the operator supplied is the only source.
    """
    if args.runs_file is not None:
        return None
    return resolve_run_subscriptions(
        client, args.repository, runs, base_subscriptions=subscriptions
    )


def main(argv: Sequence[str] | None = None, client: GitHubClient | None = None) -> int:
    """Entry point. See the module docstring for the exit-code contract."""
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    contract_error = pinned_contract_error(args)
    if contract_error is not None:
        print(f"[FAIL] {contract_error}", file=sys.stderr)
        return EXIT_CONFIG

    if client is None:
        client = GhCliClient()

    if _needs_credentials(args) and not _authenticated(client):
        print(
            "[FAIL] gh is not authenticated. Run `gh auth login` (or export a "
            "token with repo and workflow scope) before planning against the "
            "live API or confirming a cancellation.",
            file=sys.stderr,
        )
        return EXIT_AUTH

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
        subscriptions_by_run=_resolve_live_subscriptions(
            args, client, runs, subscriptions
        ),
    )

    print(format_report(manifest))

    manifest_path = resolve_manifest_path(args)
    if manifest_path is not None:
        try:
            write_manifest(manifest_path, manifest)
        except OSError as exc:
            print(f"[FAIL] cannot write manifest: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"recovery manifest written to {manifest_path}")

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

    # resolve_manifest_path always yields a path under --confirm; restating the
    # default keeps the retry instruction _execute prints pointing at a real
    # file without asking the reader to trace the branch above.
    confirmed_manifest_path = (
        manifest_path if manifest_path is not None else _DEFAULT_MANIFEST_PATH
    )
    return _execute(client, manifest, args.repository, confirmed_manifest_path)


if __name__ == "__main__":
    sys.exit(main())
