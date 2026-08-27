"""Fail-closed recovery planning for a bulk Actions cancellation.

Issue #4835. On 2026-08-09 a panic rollback cancelled 818 of 820 queued or
in-progress workflow runs across 41 PR branches with no mapping from the
cancelled runs to the events that would regenerate them. Dozens of PRs were
left showing cancelled, pending, or permanently absent required checks, and
close/reopen did not recover all of them because some workflows did not
subscribe to ``reopened``.

The policy this module encodes: a run whose cancellation would remove a
*required* context may only be cancelled when the operator names a recovery
event AND the workflow demonstrably subscribes to it. A run that publishes no
required context needs no recovery event. Anything unverifiable blocks the
whole batch, because a partially-verified bulk cancel is the incident.

The required-context set is a parameter, never a second copy. The caller passes
``REQUIRED_CONTEXTS`` from ``scripts/ci/ruleset_required_contexts.py``, whose
own comment states the reason a duplicate is forbidden: "A second baseline would
recreate the drift this check detects."
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .workflow_event_subscriptions import (
    RECOVERY_EVENTS,
    WorkflowSubscriptions,
    declared_required_contexts,
    subscribes_to,
)

__all__ = [
    "MANIFEST_VERSION",
    "BlastRadius",
    "RecoveryEntry",
    "RecoveryManifest",
    "WorkflowRun",
    "active_statuses",
    "dedupe_runs",
    "manifest_to_dict",
    "plan_recovery",
    "run_from_mapping",
    "summarize_blast_radius",
]

MANIFEST_VERSION = 1

_ACTIVE_STATUSES = ("queued", "in_progress")


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """One workflow run that a bulk cancellation would kill.

    ``jobs_verified`` distinguishes a run whose job records were actually read
    from GitHub from one where the jobs endpoint returned zero records because
    they have not materialized yet (see ``workflow_runs.run_contexts``). A run
    loaded from a recorded manifest (:func:`run_from_mapping`) defaults to
    verified: that path already fails closed on a missing ``contexts`` key, so
    an explicit (even empty) list there is trusted as the real snapshot.
    """

    run_id: int
    workflow_name: str
    pr_number: int
    branch: str
    event: str
    status: str
    contexts: tuple[str, ...]
    jobs_verified: bool = True


@dataclass(frozen=True, slots=True)
class RecoveryEntry:
    """The recovery verdict for one run.

    ``verification`` records *what was actually checked*, so ``verified: true``
    is never ambiguous about how it was reached:

    - ``subscription``: :func:`subscribes_to` matched a trigger the workflow
      file declares.
    - ``rerun``: no subscription was needed, because the operator will re-run
      this run by its ``run_id`` through the Actions API.
    - ``not-required``: the run publishes no required context, so no recovery
      event applies.
    - ``none``: nothing verified; the entry is blocked and ``blocked_reason``
      says why.

    ``jobs_verified`` mirrors :attr:`WorkflowRun.jobs_verified` so a manifest
    replayed through ``--runs-file`` carries the same fail-closed state it was
    written with, rather than defaulting back to trusted.
    """

    run_id: int
    pr_number: int
    branch: str
    workflow_name: str
    event: str
    status: str
    required_contexts: tuple[str, ...]
    other_contexts: tuple[str, ...]
    recovery_event: str | None
    verified: bool
    blocked_reason: str | None
    verification: str = "none"
    jobs_verified: bool = True


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """What a cancellation would touch, counted before any mutation."""

    run_count: int
    pr_count: int
    branch_count: int
    workflow_count: int
    queued_runs: int
    in_progress_runs: int
    required_context_count: int


@dataclass(frozen=True, slots=True)
class RecoveryManifest:
    """The full plan: every entry, the blocked subset, and the blast radius."""

    generated_at: str
    repository: str
    recovery_event: str | None
    blast_radius: BlastRadius
    entries: tuple[RecoveryEntry, ...] = field(default_factory=tuple)

    @property
    def blocked(self) -> tuple[RecoveryEntry, ...]:
        """Entries with no verified recovery path."""
        return tuple(entry for entry in self.entries if not entry.verified)

    @property
    def is_safe(self) -> bool:
        """True when every entry has a verified recovery path."""
        return not self.blocked


def run_from_mapping(payload: Mapping[str, Any]) -> WorkflowRun:
    """Build a :class:`WorkflowRun` from a JSON object.

    Raises:
        ValueError: when a field is missing or has the wrong type. Failing here
            is deliberate: a run record silently defaulted to an empty context
            tuple would be classified as non-required and cancelled without a
            recovery event, which is the exact failure this guard exists to
            prevent.
    """
    try:
        contexts = payload["contexts"]
        if isinstance(contexts, str) or not isinstance(contexts, Iterable):
            raise ValueError(f"contexts must be a list of strings, got: {contexts!r}")
        # An absent key keeps the documented default of True. An explicit false
        # is honored so a manifest written for an unmaterialized run replays as
        # unverified instead of silently regaining trust on the round trip.
        recorded_verified = payload.get("jobs_verified")
        return WorkflowRun(
            run_id=int(payload["run_id"]),
            workflow_name=str(payload["workflow_name"]),
            pr_number=int(payload["pr_number"]),
            branch=str(payload["branch"]),
            event=str(payload["event"]),
            status=str(payload["status"]),
            contexts=tuple(str(item) for item in contexts),
            jobs_verified=True if recorded_verified is None else bool(recorded_verified),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"malformed workflow run record: {payload!r}") from exc


def dedupe_runs(runs: Iterable[WorkflowRun]) -> list[WorkflowRun]:
    """Drop repeated run ids, keeping the first occurrence.

    Actions list endpoints can repeat a run across page boundaries when runs
    complete during pagination, and a repeated run would inflate every count in
    the blast radius the operator reads before confirming.
    """
    seen: set[int] = set()
    unique: list[WorkflowRun] = []
    for run in runs:
        if run.run_id in seen:
            continue
        seen.add(run.run_id)
        unique.append(run)
    return unique


def summarize_blast_radius(runs: Sequence[WorkflowRun], required: frozenset[str]) -> BlastRadius:
    """Count what a cancellation of ``runs`` would touch."""
    required_contexts = {
        context for run in runs for context in run.contexts if context in required
    }
    return BlastRadius(
        run_count=len(runs),
        pr_count=len({run.pr_number for run in runs}),
        branch_count=len({run.branch for run in runs}),
        workflow_count=len({run.workflow_name for run in runs}),
        queued_runs=sum(1 for run in runs if run.status == "queued"),
        in_progress_runs=sum(1 for run in runs if run.status == "in_progress"),
        required_context_count=len(required_contexts),
    )


def _classify(
    run: WorkflowRun,
    required: frozenset[str],
    subscriptions: Mapping[str, WorkflowSubscriptions],
    recovery_event: str | None,
) -> RecoveryEntry:
    """Decide whether one run may be cancelled.

    The required-context set is the union of two sources, never one. The API
    contributes what the jobs endpoint has materialized for this run; the
    workflow file contributes every required context its job declarations could
    publish. A queued run whose required job sits behind ``needs:`` has the
    first set empty and the second populated, and reading only the first is what
    let such a run clear as "publishes nothing required" (see
    ``workflow_event_subscriptions`` for the measured count of gated jobs).
    """
    workflow = subscriptions.get(run.workflow_name)
    from_api = {context for context in run.contexts if context in required}
    from_definition = (
        declared_required_contexts(workflow, required)
        if workflow is not None
        else frozenset()
    )
    required_contexts = tuple(sorted(from_api | from_definition))
    other_contexts = tuple(sorted(c for c in run.contexts if c not in required))

    def verdict(
        *,
        event: str | None,
        verified: bool,
        reason: str | None,
        verification: str = "none",
    ) -> RecoveryEntry:
        return RecoveryEntry(
            run_id=run.run_id,
            pr_number=run.pr_number,
            branch=run.branch,
            workflow_name=run.workflow_name,
            event=run.event,
            status=run.status,
            required_contexts=required_contexts,
            other_contexts=other_contexts,
            recovery_event=event,
            verified=verified,
            blocked_reason=reason,
            verification=verification,
            jobs_verified=run.jobs_verified,
        )

    if workflow is None:
        # Fail closed ahead of the not-required early return. Without a
        # definition the guard cannot enumerate what this run publishes, so an
        # empty context tuple is an unread question rather than an answer.
        return verdict(
            event=recovery_event,
            verified=False,
            reason=(
                f"no workflow definition found for {run.workflow_name!r}, so its "
                "published contexts cannot be determined"
            ),
        )

    if not required_contexts:
        if not run.jobs_verified:
            return verdict(
                event=None,
                verified=False,
                reason=(
                    "GitHub returned zero job records for this run; its jobs "
                    "may not have materialized yet (a queued run in this "
                    "state), so the absence of a required context cannot be "
                    "trusted (issue #4835 fail-open guard)"
                ),
            )
        return verdict(
            event=None, verified=True, reason=None, verification="not-required"
        )

    if recovery_event is None:
        return verdict(
            event=None,
            verified=False,
            reason=(
                "publishes required contexts "
                f"{', '.join(required_contexts)} and no recovery event was named"
            ),
        )

    if not subscribes_to(workflow, recovery_event):
        return verdict(
            event=recovery_event,
            verified=False,
            reason=(
                f"{run.workflow_name!r} does not subscribe to {recovery_event!r} "
                f"(declared pull_request types: "
                f"{', '.join(sorted(workflow.pull_request_types)) or 'none'})"
            ),
        )

    if workflow.has_path_filters:
        return verdict(
            event=recovery_event,
            verified=False,
            reason=(
                f"{run.workflow_name!r} subscribes to {recovery_event!r} but "
                "declares trigger path filters (paths/paths-ignore), so the "
                "event is not guaranteed to regenerate the run"
            ),
        )

    return verdict(
        event=recovery_event,
        verified=True,
        reason=None,
        verification="rerun" if recovery_event == "rerun" else "subscription",
    )


def plan_recovery(
    runs: Iterable[WorkflowRun],
    *,
    required: frozenset[str],
    subscriptions: Mapping[str, WorkflowSubscriptions],
    recovery_event: str | None,
    repository: str,
    now: datetime | None = None,
) -> RecoveryManifest:
    """Build the recovery manifest for a proposed bulk cancellation.

    Args:
        runs: Runs the operator proposes to cancel. Duplicated run ids are
            collapsed before anything is counted.
        required: Required status check contexts for the protected branch.
        subscriptions: Workflow name to its parsed event subscriptions.
        recovery_event: The event the operator will use to regenerate cancelled
            required contexts, or None when they named none.
        repository: ``owner/repo``, recorded in the manifest.
        now: Injected clock for deterministic tests.

    Raises:
        ValueError: when ``recovery_event`` is not one of
            :data:`~scripts.github_core.workflow_event_subscriptions.RECOVERY_EVENTS`.
            An unrecognised name would otherwise block every required run with a
            confusing "does not subscribe" reason instead of naming the typo.
    """
    if recovery_event is not None and recovery_event not in RECOVERY_EVENTS:
        raise ValueError(
            f"unknown recovery event {recovery_event!r}; "
            f"expected one of {', '.join(sorted(RECOVERY_EVENTS))}"
        )

    unique = dedupe_runs(runs)
    entries = tuple(
        _classify(run, required, subscriptions, recovery_event) for run in unique
    )
    timestamp = (now or datetime.now(UTC)).isoformat()
    return RecoveryManifest(
        generated_at=timestamp,
        repository=repository,
        recovery_event=recovery_event,
        blast_radius=summarize_blast_radius(unique, required),
        entries=entries,
    )


def manifest_to_dict(manifest: RecoveryManifest) -> dict[str, Any]:
    """Serialize a manifest to a JSON-ready dict."""
    radius = manifest.blast_radius
    return {
        "version": MANIFEST_VERSION,
        "generated_at": manifest.generated_at,
        "repository": manifest.repository,
        "recovery_event": manifest.recovery_event,
        "blast_radius": {
            "runs": radius.run_count,
            "pull_requests": radius.pr_count,
            "branches": radius.branch_count,
            "workflows": radius.workflow_count,
            "queued_runs": radius.queued_runs,
            "in_progress_runs": radius.in_progress_runs,
            "required_contexts": radius.required_context_count,
        },
        "safe": manifest.is_safe,
        "entries": [
            {
                "run_id": entry.run_id,
                "pull_request": entry.pr_number,
                "branch": entry.branch,
                "workflow": entry.workflow_name,
                "event": entry.event,
                "status": entry.status,
                "required_contexts": list(entry.required_contexts),
                "other_contexts": list(entry.other_contexts),
                "recovery_event": entry.recovery_event,
                "verified": entry.verified,
                "verification": entry.verification,
                "jobs_verified": entry.jobs_verified,
                "blocked_reason": entry.blocked_reason,
            }
            for entry in manifest.entries
        ],
    }


def active_statuses() -> tuple[str, ...]:
    """Run statuses a bulk cancellation can act on."""
    return _ACTIVE_STATUSES
