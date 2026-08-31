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
from urllib.parse import quote

from .protocol import GitHubClient
from .recovery_manifest import WorkflowRun, active_statuses

__all__ = [
    "PAGE_SIZE",
    "CancellationOutcome",
    "JobsNotMaterializedError",
    "PullRequestTarget",
    "cancel_runs",
    "collect_runs_for_targets",
    "iter_paginated",
    "run_contexts",
]

# GitHub caps `per_page` at 100 for the Actions endpoints used here.
PAGE_SIZE = 100

# A single branch's active runs are bounded by the workflow count, but a bulk
# operation spans dozens of branches. Cap the walk so a paging bug cannot spin
# forever against a live API.
_MAX_PAGES = 50


def _path_segment(value: str) -> str:
    """Percent-encode a value used inside a REST path.

    ``owner/repo`` is two segments, so the separator is preserved while every
    other reserved character is escaped.
    """
    return quote(value, safe="/")


def _query_value(value: str) -> str:
    """Percent-encode a value used as a REST query-string parameter.

    Nothing is safe here, the slash included. Git permits ``&`` and ``+`` in a
    refname, and ``?`` and ``#`` reach this code from a caller that read a name
    from an API payload rather than from git. Interpolated raw, a branch such as
    ``feat/a&status=completed`` appends a second ``status`` parameter that
    GitHub resolves ahead of the intended one, and the walk then enumerates a
    different run set than the one the operator is about to cancel.
    """
    return quote(value, safe="")


@dataclass(frozen=True, slots=True)
class PullRequestTarget:
    """One pull request the operator asked to cancel runs for.

    The Actions run-list endpoint filters on ``branch``, which matches the head
    branch *name* and nothing else. A name is unique inside one repository and
    not across repositories, so two open pull requests from two different forks
    can both use ``patch-1`` and both appear under that filter. Cancelling on
    the branch name alone therefore reaches into a pull request the operator
    never named, which for ``--pr N`` means killing a stranger's CI.

    ``head_repository`` is the discriminator that closes it: a branch name is
    unique within its repository, so ``(branch, head_repository)`` identifies
    exactly one open pull request. It is deliberately not the head SHA. A SHA
    identifies one commit, and a pull request can carry queued runs for an
    earlier commit that are still the operator's to cancel, so filtering on it
    would silently drop runs the batch is supposed to cover.

    Attributes:
        pr_number: The pull request number, recorded on every run it owns.
        branch: The head branch name, passed to the Actions ``branch`` filter.
        head_repository: ``owner/repo`` of the head branch's repository, which
            equals the base repository for a same-repo pull request and the
            fork for a cross-repository one.
    """

    pr_number: int
    branch: str
    head_repository: str


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


class JobsNotMaterializedError(RuntimeError):
    """The jobs endpoint returned zero records for a run that must have some.

    Every valid workflow declares at least one job, so a genuinely empty
    ``jobs`` response is not evidence the run publishes no required context.
    It means GitHub has not finished materializing job records for the run
    yet, which happens for a run still in ``queued`` state. Issue #4835: a
    2026-08-09 panic rollback taught this codebase that an unverifiable run
    must fail closed, not be waved through as safe.
    """


def run_contexts(client: GitHubClient, repository: str, run_id: int) -> tuple[str, ...]:
    """Return the check-run context names one workflow run publishes.

    A required status check is matched by branch protection against the
    check-run name, which for GitHub Actions is the job's ``name:`` (or its job
    id when unnamed). So the run's job names are exactly the contexts that
    disappear when the run is cancelled.

    Duplicate names collapse: two jobs of one run may deliberately share a name
    so branch protection sees one required context.

    Raises:
        JobsNotMaterializedError: when the jobs endpoint returns zero records.
            Callers must not treat this the same as a verified empty context
            set; see the exception's docstring.
    """
    endpoint = f"repos/{_path_segment(repository)}/actions/runs/{run_id}/jobs"
    names: list[str] = []
    saw_any_job = False
    for job in iter_paginated(client, endpoint, "jobs"):
        saw_any_job = True
        name = job.get("name")
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    if not saw_any_job:
        raise JobsNotMaterializedError(
            f"run {run_id} in {repository!r} returned zero job records"
        )
    return tuple(names)


def _branch_runs(
    client: GitHubClient, repository: str, branch: str, status: str
) -> Iterator[dict[str, Any]]:
    endpoint = (
        f"repos/{_path_segment(repository)}/actions/runs"
        f"?branch={_query_value(branch)}&status={_query_value(status)}"
    )
    yield from iter_paginated(client, endpoint, "workflow_runs")


def run_head_repository(payload: Mapping[str, Any]) -> str | None:
    """Read ``head_repository.full_name`` off a workflow-run payload.

    Returns None when the field is absent or malformed, which callers must
    treat as "this run cannot be attributed", never as a match.
    """
    head_repository = payload.get("head_repository")
    if not isinstance(head_repository, Mapping):
        return None
    full_name = head_repository.get("full_name")
    return full_name if isinstance(full_name, str) and full_name else None


def collect_runs_for_targets(
    client: GitHubClient,
    repository: str,
    targets: Sequence[PullRequestTarget],
    *,
    statuses: Sequence[str] | None = None,
) -> list[WorkflowRun]:
    """Enumerate the active workflow runs each pull request owns.

    The Actions ``branch`` filter matches a head branch *name*, which is not
    unique across forks, so every returned run is checked against the target's
    ``head_repository`` before it is attributed. See
    :class:`PullRequestTarget` for why that is the right identity and why the
    head SHA is not.

    Args:
        client: Transport used for every read. No writes happen here.
        repository: ``owner/repo`` of the base repository being enumerated.
        targets: The pull requests to collect runs for. A sequence rather than
            a branch-keyed mapping, because two open pull requests from two
            forks can share one branch name and a mapping would silently drop
            one of them.
        statuses: Run statuses to enumerate. Defaults to queued and
            in_progress, the two states a cancellation can act on.

    Returns:
        One :class:`WorkflowRun` per distinct run id, with its published check
        contexts resolved. Three kinds of run are skipped rather than
        attributed, and every one of them is the safe direction, since a run
        left out of the inventory is a run this tool will not cancel:

        - A missing or non-numeric ``id``. It cannot be cancelled by id, so
          including it would only inflate the blast radius.
        - A ``head_repository`` that does not match the target's. It belongs to
          a different pull request that happens to share the branch name.
        - A ``head_repository`` that is absent or malformed. The run cannot be
          attributed at all, and an unattributable run must not be assumed to
          be the operator's.

        A run whose jobs have not materialized yet
        (:class:`JobsNotMaterializedError`) is still included, with
        ``contexts=()`` and ``jobs_verified=False`` so
        :func:`~scripts.github_core.recovery_manifest.plan_recovery` blocks it
        instead of treating the empty context set as verified-safe.
    """
    wanted = tuple(statuses) if statuses is not None else active_statuses()
    collected: dict[int, WorkflowRun] = {}

    for target in targets:
        for status in wanted:
            for payload in _branch_runs(client, repository, target.branch, status):
                raw_id = payload.get("id")
                if not isinstance(raw_id, int):
                    continue
                if raw_id in collected:
                    continue
                if run_head_repository(payload) != target.head_repository:
                    continue
                try:
                    contexts = run_contexts(client, repository, raw_id)
                    jobs_verified = True
                except JobsNotMaterializedError:
                    # Fail closed (issue #4835): treat an unmaterialized run
                    # as having unverifiable required context rather than
                    # silently classifying it as safe to cancel.
                    contexts = ()
                    jobs_verified = False
                collected[raw_id] = WorkflowRun(
                    run_id=raw_id,
                    workflow_name=str(payload.get("name") or ""),
                    pr_number=target.pr_number,
                    branch=target.branch,
                    event=str(payload.get("event") or ""),
                    status=str(payload.get("status") or status),
                    contexts=contexts,
                    jobs_verified=jobs_verified,
                    workflow_path=str(payload.get("path") or ""),
                    head_repo=target.head_repository,
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
        endpoint = f"repos/{_path_segment(repository)}/actions/runs/{run_id}/cancel"
        try:
            client.rest_post(endpoint, {})
        except (RuntimeError, OSError, ValueError) as exc:
            failed.append((run_id, str(exc) or exc.__class__.__name__))
            continue
        cancelled.append(run_id)
    return CancellationOutcome(cancelled=tuple(cancelled), failed=tuple(failed))
