"""Enumerate and cancel Actions workflow runs for open pull requests.

Issue #4835. Split out of ``scripts/bulk_cancel_guard.py`` so the enumeration
and mutation boundary can be tested against a fake client without driving the
CLI, and so neither file grows past the 500-line taste ceiling.

Every function here takes a :class:`~scripts.github_core.protocol.GitHubClient`,
so tests substitute a fake and never reach the network. Nothing in this module
mutates unless the caller explicitly calls :func:`cancel_runs`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.github_core.protocol import GitHubClient
from scripts.github_core.recovery_manifest import WorkflowRun, active_statuses

__all__ = [
    "PAGE_SIZE",
    "CancellationOutcome",
    "cancel_runs",
    "collect_runs_for_branches",
    "iter_paginated",
    "run_contexts",
]

# GitHub caps `per_page` at 100 for the Actions endpoints used here.
PAGE_SIZE = 100

# A single branch's active runs are bounded by the workflow count, but a bulk
# operation spans dozens of branches. Cap the walk so a paging bug cannot spin
# forever against a live API.
_MAX_PAGES = 50


@dataclass(frozen=True, slots=True)
class CancellationOutcome:
    """What actually happened when the operator confirmed a cancellation."""

    cancelled: tuple[int, ...]
    failed: tuple[tuple[int, str], ...]

    @property
    def is_complete(self) -> bool:
        """True when every requested run was cancelled."""
        return not self.failed


def iter_paginated(
    client: GitHubClient, endpoint: str, items_key: str
) -> Iterator[dict[str, Any]]:
    """Yield every item across the paginated GitHub REST endpoint.

    Stops on the first short page, on an empty page, or at ``_MAX_PAGES``. The
    separator between ``endpoint`` and the paging parameters is chosen from
    whether the endpoint already carries a query string, so a caller may pass
    filters such as ``?status=queued`` without corrupting the URL.
    """
    separator = "&" if "?" in endpoint else "?"
    for page in range(1, _MAX_PAGES + 1):
        url = f"{endpoint}{separator}per_page={PAGE_SIZE}&page={page}"
        payload = client.rest_get(url)
        items = payload.get(items_key)
        if not isinstance(items, list) or not items:
            return
        for item in items:
            if isinstance(item, Mapping):
                yield dict(item)
        if len(items) < PAGE_SIZE:
            return


def run_contexts(client: GitHubClient, repository: str, run_id: int) -> tuple[str, ...]:
    """Return the check-run context names one workflow run publishes.

    A required status check is matched by branch protection against the
    check-run name, which for GitHub Actions is the job's ``name:`` (or its job
    id when unnamed). So the run's job names are exactly the contexts that
    disappear when the run is cancelled.

    Duplicate names collapse: two jobs of one run may deliberately share a name
    so branch protection sees one required context.
    """
    endpoint = f"repos/{repository}/actions/runs/{run_id}/jobs"
    names: list[str] = []
    for job in iter_paginated(client, endpoint, "jobs"):
        name = job.get("name")
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return tuple(names)


def _branch_runs(
    client: GitHubClient, repository: str, branch: str, status: str
) -> Iterator[dict[str, Any]]:
    endpoint = f"repos/{repository}/actions/runs?branch={branch}&status={status}"
    yield from iter_paginated(client, endpoint, "workflow_runs")


def collect_runs_for_branches(
    client: GitHubClient,
    repository: str,
    branches: Mapping[str, int],
    *,
    statuses: Sequence[str] | None = None,
) -> list[WorkflowRun]:
    """Enumerate the active workflow runs for each branch.

    Args:
        client: Transport used for every read. No writes happen here.
        repository: ``owner/repo``.
        branches: Branch name to the pull request number it belongs to.
        statuses: Run statuses to enumerate. Defaults to queued and
            in_progress, the two states a cancellation can act on.

    Returns:
        One :class:`WorkflowRun` per distinct run id, with its published check
        contexts resolved. A run whose id is missing or non-numeric is skipped:
        it cannot be cancelled by id, so including it would inflate the blast
        radius with a run the tool could never act on.
    """
    wanted = tuple(statuses) if statuses is not None else active_statuses()
    collected: dict[int, WorkflowRun] = {}

    for branch, pr_number in branches.items():
        for status in wanted:
            for payload in _branch_runs(client, repository, branch, status):
                raw_id = payload.get("id")
                if not isinstance(raw_id, int):
                    continue
                if raw_id in collected:
                    continue
                collected[raw_id] = WorkflowRun(
                    run_id=raw_id,
                    workflow_name=str(payload.get("name") or ""),
                    pr_number=pr_number,
                    branch=branch,
                    event=str(payload.get("event") or ""),
                    status=str(payload.get("status") or status),
                    contexts=run_contexts(client, repository, raw_id),
                )
    return list(collected.values())


def cancel_runs(
    client: GitHubClient, repository: str, run_ids: Sequence[int]
) -> CancellationOutcome:
    """Cancel each run, recording per-run failures instead of aborting.

    A bulk cancellation that stops on the first error leaves the batch in a
    state nobody recorded: some runs killed, some untouched, and no manifest
    entry marking which. Every failure is captured with its message so the
    caller can report exactly which runs still need attention.
    """
    cancelled: list[int] = []
    failed: list[tuple[int, str]] = []
    for run_id in run_ids:
        endpoint = f"repos/{repository}/actions/runs/{run_id}/cancel"
        try:
            client.rest_post(endpoint, {})
        except (RuntimeError, OSError, ValueError) as exc:
            failed.append((run_id, str(exc) or exc.__class__.__name__))
            continue
        cancelled.append(run_id)
    return CancellationOutcome(cancelled=tuple(cancelled), failed=tuple(failed))
