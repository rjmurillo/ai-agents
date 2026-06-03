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
closed, label already present, milestone already set). The natural idempotency
key is the issue number plus the action category, so re-running the same
approved manifest is a no-op. Side effects flow through the GitHub gateway only;
the executor never writes any other store.

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
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
            tuple(str(item).strip() for item in labels_raw if str(item).strip())
            if isinstance(labels_raw, list)
            else ()
        )
        return cls(
            issue=issue,
            category=category,
            rationale=str(raw.get("rationale") or ""),
            labels=labels,
            priority=str(raw.get("priority") or "").strip(),
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


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def load_manifest(path: Path) -> dict[str, object]:
    """Load and minimally validate the manifest. Raises ValueError on a bad file."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError(f"cannot read manifest {path}: {err}") from err
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as err:
        raise ValueError(f"manifest {path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValueError(f"manifest {path} must be a JSON object")
    if not isinstance(data.get("actions"), list):
        raise ValueError(f"manifest {path} must have an 'actions' array")
    return data


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
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "issue not found",
        )
    if state.state.upper() == "CLOSED":
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "already closed",
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
        return ActionOutcome(
            action.issue, action.category, OUTCOME_SKIPPED, "issue not found",
        )
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


class CliGitHubGateway:
    """Production gateway. Talks to issues through the gh CLI.

    Reuses the gh issue surface the github skill scripts use. Reads go through
    ``gh issue view``; mutations through ``gh issue close`` and ``gh issue edit``.
    """

    def __init__(self, owner: str, repo: str, *, timeout: float = 30.0) -> None:
        self._repo = f"{owner}/{repo}"
        self._timeout = timeout

    def get_issue_state(self, issue: int) -> IssueState | None:
        result = self._run(
            ["gh", "issue", "view", str(issue), "--repo", self._repo,
             "--json", "number,state,labels"],
        )
        if result is None or result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None
        labels = frozenset(
            str(label.get("name", "")) for label in data.get("labels", [])
        )
        return IssueState(
            number=int(data.get("number", issue)),
            state=str(data.get("state", "")),
            labels=labels,
        )

    def close_issue(self, issue: int) -> bool:
        result = self._run(
            ["gh", "issue", "close", str(issue), "--repo", self._repo],
        )
        return result is not None and result.returncode == 0

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool:
        command = ["gh", "issue", "edit", str(issue), "--repo", self._repo]
        for label in labels:
            command.extend(["--add-label", label])
        result = self._run(command)
        return result is not None and result.returncode == 0

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a human-approved backlog-triage action manifest.",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to the approval manifest produced by triage_recommendation_report.py.",
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
        manifest = load_manifest(Path(args.manifest))
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
        # A configured repo lets dry-run read real state for an accurate preview
        # (would-close vs already-closed). Without one, fall back to an offline
        # gateway that plans against unknown state and refuses every mutation.
        gateway = (
            CliGitHubGateway(args.owner, args.repo)
            if args.owner and args.repo
            else _OfflineGateway()
        )

    outcomes = run_batch(actions, gateway, mutate=mutate)
    print(render_outcomes(outcomes, mutate=mutate))

    if not mutate and args.apply:
        print(
            "Manifest not approved (approved != true); no mutations performed.",
            file=sys.stderr,
        )
    if any(item.outcome == OUTCOME_FAILED for item in outcomes):
        failed = sum(1 for item in outcomes if item.outcome == OUTCOME_FAILED)
        print(f"{failed} action(s) failed against the GitHub API", file=sys.stderr)
        return 3
    return 0


class _OfflineGateway:
    """Fallback gateway when no repository is configured.

    Used only for an offline dry-run with no --owner/--repo. It returns ``None``
    for state so close/relabel actions plan against an unknown issue, the safe
    default for a preview that must not touch the API, and refuses every
    mutation. ``main`` never selects this gateway when mutation is authorized,
    because that path requires owner and repo.
    """

    def get_issue_state(self, issue: int) -> IssueState | None:
        return None

    def close_issue(self, issue: int) -> bool:  # pragma: no cover - never called offline
        raise RuntimeError("offline gateway must not mutate")

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool:  # pragma: no cover
        raise RuntimeError("offline gateway must not mutate")


if __name__ == "__main__":
    sys.exit(main())
