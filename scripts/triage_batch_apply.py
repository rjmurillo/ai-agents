#!/usr/bin/env python3
"""Apply a human-approved backlog-triage action manifest, idempotently.

Phase 3 of the backlog-triage workflow (issue #2261, epic #1799). Consumes the
approval manifest written by ``triage_recommendation_report.py`` and applies the
approved actions (close, relabel, prioritize) to GitHub issues.

Human-approval gate: this executor mutates nothing unless BOTH hold:

* the manifest has ``"approved": true`` (a human edited it to approve), and
* the caller passes ``--apply``.

Either condition missing means dry-run: every action is reported as planned but
no GitHub state changes. This is the acceptance criterion that no action runs
without explicit human approval.

Idempotency: before each mutation the executor fetches the issue's current state
and skips the action if the issue is already in the target state (already
closed or label already present). The natural idempotency key is the issue number
plus the action category, so re-running the same approved manifest is a no-op.
Side effects flow through the GitHub gateway only; the executor never writes any
other store.

Categories ``decompose`` and ``batch`` are advisory only. They have no automated
mutation, so they are always reported as skipped with a reason; a human handles
them out of band.

Exit codes follow ADR-035:
    0 - Success (all approved actions applied, skipped, or planned)
    2 - Config error (manifest missing, unreadable, or malformed)
    3 - External error (one or more mutations failed against the GitHub API)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Allow standalone invocation (python3 scripts/triage_batch_apply.py) to resolve
# sibling packages: put the repo root, not just scripts/, on sys.path. Idempotent
# and a no-op under pytest, where the root is already importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.verify_issue_close import (  # noqa: E402
    IssueComment,
    check_unresolved_scope,
    extract_commit_shas,
    extract_pr_numbers,
    unverified_claims,
)

# Action categories mirror scripts/triage_recommendation_report.py.
ACTION_CLOSE = "close"
ACTION_RELABEL = "relabel"
ACTION_PRIORITIZE = "prioritize"
ACTION_DECOMPOSE = "decompose"
ACTION_BATCH = "batch"

# Categories with no automated mutation; surfaced for human follow-up.
ADVISORY_CATEGORIES = frozenset({ACTION_DECOMPOSE, ACTION_BATCH})

OUTCOME_APPLIED = "applied"
OUTCOME_SKIPPED = "skipped"
OUTCOME_PLANNED = "planned"
OUTCOME_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IssueState:
    """The slice of an issue's current state the executor checks before mutating."""

    number: int
    state: str
    labels: frozenset[str]


@dataclass(frozen=True, slots=True)
class ManifestAction:
    """One approved action read from the manifest, mapped to a typed value."""

    issue: int
    category: str
    rationale: str = ""
    labels: tuple[str, ...] = ()
    priority: str = ""
    reproduction_verified: bool = False

    @classmethod
    def from_raw(cls, raw: object) -> ManifestAction | None:
        """Map one manifest entry to a typed action, or None if invalid.

        The manifest is a human-edited artifact, so each entry is untrusted on
        the way in. A missing issue, non-integer issue, or unknown category
        means the entry is dropped rather than crashing the whole batch.
        """

        if not isinstance(raw, dict):
            return None
        issue = _positive_int(raw.get("issue"))
        if issue is None:
            return None
        category = str(raw.get("category") or "").strip().lower()
        if not category:
            return None
        labels_raw = raw.get("labels")
        labels = (
            tuple(item.strip() for item in labels_raw if isinstance(item, str) and item.strip())
            if isinstance(labels_raw, list)
            else ()
        )
        reproduction_raw = raw.get("reproduction_verified")
        reproduction_verified = reproduction_raw is True
        return cls(
            issue=issue,
            category=category,
            rationale=str(raw.get("rationale") or ""),
            labels=labels,
            priority=str(raw.get("priority") or "").strip(),
            reproduction_verified=reproduction_verified,
        )


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    """The result of attempting one action: applied, skipped, planned, or failed."""

    issue: int
    category: str
    outcome: str
    detail: str = ""


class GitHubGateway(Protocol):
    """Boundary for all GitHub mutations and reads.

    Domain logic depends on this Protocol, not on the gh CLI. Tests substitute a
    fake; production uses ``CliGitHubGateway``. This keeps the executor's
    idempotency and approval logic testable without touching the network.
    """

    def get_issue_state(self, issue: int) -> IssueState | None: ...

    def close_issue(self, issue: int) -> bool: ...

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool: ...

    def commit_exists(self, sha: str) -> bool: ...

    def pr_is_merged(self, pr: int) -> bool: ...

    def get_issue_comments(self, issue: int) -> list[IssueComment] | None:
        """Return issue comments, or None on API failure.

        None means the fetch failed (rate-limited, network error). The caller
        must treat None as blocking (issue #4640 principle: a failed lookup
        must never be treated as "no data found").
        """
        ...

    def get_pr_merge_time(self, pr: int) -> datetime.datetime | None:
        """Return the merge timestamp of a PR, or None if unavailable."""
        ...

    def get_commit_time(self, sha: str) -> datetime.datetime | None:
        """Return a commit's timestamp, or None if unavailable."""
        ...


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def load_manifest_json(raw: str, source: str) -> dict[str, object]:
    """Load and minimally validate manifest JSON. Raises ValueError on bad input."""

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as err:
        raise ValueError(f"manifest {source} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValueError(f"manifest {source} must be a JSON object")
    if not isinstance(data.get("actions"), list):
        raise ValueError(f"manifest {source} must have an 'actions' array")
    return data


def load_manifest(path: Path) -> dict[str, object]:
    """Load and minimally validate the manifest. Raises ValueError on a bad file."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError(f"cannot read manifest {path}: {err}") from err
    return load_manifest_json(raw, str(path))


def parse_actions(manifest: dict[str, object]) -> list[ManifestAction]:
    """Map the manifest's raw action entries to typed actions, dropping invalid ones."""

    raw_actions = manifest.get("actions")
    if not isinstance(raw_actions, list):
        return []
    actions: list[ManifestAction] = []
    for raw in raw_actions:
        action = ManifestAction.from_raw(raw)
        if action is not None:
            actions.append(action)
    return actions


def is_mutation_authorized(manifest: dict[str, object], apply_flag: bool) -> bool:
    """Mutation runs only when the manifest is approved AND --apply was passed."""

    return manifest.get("approved") is True and apply_flag


def apply_action(
    action: ManifestAction,
    gateway: GitHubGateway,
    *,
    mutate: bool,
) -> ActionOutcome:
    """Apply (or plan) one action idempotently.

    When ``mutate`` is False, returns a PLANNED or SKIPPED outcome and touches
    nothing. When True, checks the current state, skips if already in target
    state, otherwise performs the mutation through the gateway.
    """

    if action.category in ADVISORY_CATEGORIES:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED,
            "advisory only; handle manually",
        )
    if action.category == ACTION_CLOSE:
        return _apply_close(action, gateway, mutate=mutate)
    if action.category in (ACTION_RELABEL, ACTION_PRIORITIZE):
        return _apply_labels(action, gateway, mutate=mutate)
    return ActionOutcome(
        action.issue, action.category, OUTCOME_SKIPPED,
        f"unknown category {action.category!r}",
    )


def _apply_close(
    action: ManifestAction, gateway: GitHubGateway, *, mutate: bool,
) -> ActionOutcome:
    state = gateway.get_issue_state(action.issue)
    if state is None:
        return _unavailable_state_outcome(action, mutate=mutate, planned_detail="would close")
    if state.state.upper() == "CLOSED":
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "already closed",
        )
    # Epic guard (#2481): a narrowly-scoped automated close must never take down
    # an epic. Closing an epic stays a human decision regardless of mutate mode.
    if any(label.casefold() == "epic" for label in state.labels):
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED,
            "epic close requires human review",
        )
    # Citation-truth gate (#2481): if the rationale claims "resolved by commit X"
    # or "via PR #N", that commit must exist and that PR must be merged, or the
    # close is aborted. A rationale that cites neither (stale, superseded) passes.
    unverified = unverified_claims(
        action.rationale,
        commit_exists=gateway.commit_exists,
        pr_is_merged=gateway.pr_is_merged,
    )
    if unverified:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED,
            f"close aborted: unverified {', '.join(unverified)}",
        )
    # Reproduction gate (#4624): a verified citation (PR merged on main, or
    # commit exists) is necessary but not sufficient. The issue's falsifiable
    # reproduction must have been run against main and passed. Without this,
    # the campaign can close an issue whose defect is still reproducible.
    cited_prs = extract_pr_numbers(action.rationale)
    cited_shas = extract_commit_shas(action.rationale)
    if (cited_prs or cited_shas) and not action.reproduction_verified:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED,
            "close aborted: reproduction not verified against main "
            "(reproduction_verified must be true when citing a PR or commit)",
        )
    # Unresolved-scope gate (#4625): if a human commented AFTER the fix
    # evidence, the issue may have unaddressed scope. Block and report.
    fix_ts: datetime.datetime | None = None
    for pr_num in cited_prs:
        fix_ts = gateway.get_pr_merge_time(pr_num)
        if fix_ts is not None:
            break
    if fix_ts is None:
        # A rationale may cite a commit and no pull request. Without this the
        # gate below was skipped outright, so a commit-only closure never
        # checked for unresolved scope: the exact hole #4625 describes, reached
        # by a different route. Refs #4625.
        for sha in cited_shas:
            fix_ts = gateway.get_commit_time(sha)
            if fix_ts is not None:
                break
    if (cited_prs or cited_shas) and fix_ts is None:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED,
            "close aborted: cannot determine fix timestamp from cited "
            "PR(s) or commit(s)",
        )
    if fix_ts is not None:
        comments = gateway.get_issue_comments(action.issue)
        if comments is None:
            # Failed fetch blocks the close (issue #4640 principle).
            return ActionOutcome(
                action.issue, action.category, OUTCOME_SKIPPED,
                "close aborted: comment fetch failed, cannot verify scope",
            )
        scope_blocks = check_unresolved_scope(comments, fix_ts)
        if scope_blocks:
            reasons = "; ".join(b.reason for b in scope_blocks[:3])
            return ActionOutcome(
                action.issue, action.category, OUTCOME_SKIPPED,
                f"close aborted: unaddressed post-fix comment(s): {reasons}",
            )
    if not mutate:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_PLANNED, "would close",
        )
    if gateway.close_issue(action.issue):
        return ActionOutcome(action.issue, action.category, OUTCOME_APPLIED, "closed")
    return ActionOutcome(
        action.issue, action.category, OUTCOME_FAILED, "close failed",
    )


def _apply_labels(
    action: ManifestAction, gateway: GitHubGateway, *, mutate: bool,
) -> ActionOutcome:
    target_labels = _target_labels(action)
    if not target_labels:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "no labels to apply",
        )
    state = gateway.get_issue_state(action.issue)
    if state is None:
        detail = "would add " + ", ".join(target_labels)
        return _unavailable_state_outcome(action, mutate=mutate, planned_detail=detail)
    missing = [label for label in target_labels if label not in state.labels]
    if not missing:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "labels already present",
        )
    detail = ", ".join(missing)
    if not mutate:
        return ActionOutcome(
            action.issue, action.category, OUTCOME_PLANNED, f"would add {detail}",
        )
    if gateway.add_labels(action.issue, missing):
        return ActionOutcome(
            action.issue, action.category, OUTCOME_APPLIED, f"added {detail}",
        )
    return ActionOutcome(
        action.issue, action.category, OUTCOME_FAILED, f"label add failed: {detail}",
    )


def _target_labels(action: ManifestAction) -> list[str]:
    if action.category == ACTION_PRIORITIZE and action.priority:
        return [f"priority:{action.priority}"]
    return [label for label in action.labels if label]


def _unavailable_state_outcome(
    action: ManifestAction, *, mutate: bool, planned_detail: str,
) -> ActionOutcome:
    if mutate:
        return ActionOutcome(
            action.issue,
            action.category,
            OUTCOME_FAILED,
            "issue state unavailable",
        )
    return ActionOutcome(
        action.issue,
        action.category,
        OUTCOME_PLANNED,
        f"issue state unavailable; {planned_detail}",
    )


def run_batch(
    actions: list[ManifestAction], gateway: GitHubGateway, *, mutate: bool,
) -> list[ActionOutcome]:
    """Apply every action. A failure on one does not abort the rest."""

    return [apply_action(action, gateway, mutate=mutate) for action in actions]


def render_outcomes(outcomes: list[ActionOutcome], *, mutate: bool) -> str:
    """Render a one-line-per-action summary for the operator's terminal."""

    mode = "APPLY" if mutate else "DRY-RUN"
    lines = [f"Batch apply ({mode}): {len(outcomes)} action(s)"]
    for item in outcomes:
        detail = f" ({item.detail})" if item.detail else ""
        lines.append(f"  #{item.issue} {item.category}: {item.outcome}{detail}")
    return "\n".join(lines)



# Concrete gateway implementations live in scripts/triage_gateway.py to keep
# this file under the 500-line limit. Imported at call time in main() to avoid
# a circular import (the gateway module imports IssueState from this module).


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a human-approved backlog-triage action manifest.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--manifest",
        help="Path to the approval manifest produced by triage_recommendation_report.py.",
    )
    source.add_argument(
        "--manifest-json",
        default="",
        help="Approval manifest JSON supplied by a human workflow_dispatch input.",
    )
    source.add_argument(
        "--manifest-env",
        default="",
        help="Name of an environment variable containing approval manifest JSON.",
    )
    parser.add_argument(
        "--owner", default="", help="Repository owner (e.g. rjmurillo).",
    )
    parser.add_argument(
        "--repo", default="", help="Repository name (e.g. ai-agents).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform mutations. Without this flag the run is a dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, gateway: GitHubGateway | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = (
            load_manifest(Path(args.manifest))
            if args.manifest
            else load_manifest_json(
                args.manifest_json if args.manifest_json else os.environ.get(args.manifest_env, ""),
                "--manifest-json" if args.manifest_json else f"${args.manifest_env}",
            )
        )
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 2

    actions = parse_actions(manifest)
    mutate = is_mutation_authorized(manifest, args.apply)

    if mutate and not (args.owner and args.repo) and gateway is None:
        print(
            "--owner and --repo are required when applying mutations",
            file=sys.stderr,
        )
        return 2
    if gateway is None:
        # Late import to avoid circular dependency: triage_gateway imports
        # IssueState from this module.
        from scripts.triage_gateway import CliGitHubGateway, OfflineGateway

        # A configured repo lets dry-run read real state for an accurate
        # preview. Without one, fall back to the offline gateway.
        gateway = (
            CliGitHubGateway(args.owner, args.repo)
            if args.owner and args.repo
            else OfflineGateway()
        )

    outcomes = run_batch(actions, gateway, mutate=mutate)
    print(render_outcomes(outcomes, mutate=mutate))

    if not mutate and args.apply:
        print(
            "Manifest not approved (approved != true); no mutations performed.",
            file=sys.stderr,
        )
        return 2
    if any(item.outcome == OUTCOME_FAILED for item in outcomes):
        failed = sum(1 for item in outcomes if item.outcome == OUTCOME_FAILED)
        print(f"{failed} action(s) failed against the GitHub API", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
