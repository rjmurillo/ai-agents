#!/usr/bin/env python3
"""Aggregate AI-triage results into a recommendation report and approval manifest.

Phase 3 of the backlog-triage workflow (issue #2261, epic #1799). Consumes the
per-issue triage result JSON written by ``backlog_triage_result.py`` (Phase 2),
groups each issue's recommended actions by category (close, relabel, decompose,
prioritize, batch), and emits two artifacts:

* a machine-readable JSON manifest (the approved-action manifest) that
  ``triage_batch_apply.py`` consumes only after a human approves it; and
* a human-readable markdown render for review.

The manifest is a *proposal*, not an approval. It is read-only: this module
applies nothing and closes nothing. A human reviews the markdown, edits the
manifest to keep only approved actions, and feeds the trimmed manifest to the
batch-apply executor.

Reuses the typed parsing from ``scripts/backlog_triage_summary.py`` (Phase 2)
rather than re-implementing the wire shape, so the two stay in lockstep.

System of record: the per-issue result JSON is the source for what was triaged.
The manifest is a derived projection of those results plus the recommendation
policy below; it is fully rebuildable by re-running this module.

Exit codes follow ADR-035:
    0 - Success (an empty or missing results dir yields an empty manifest)
    1 - Logic error (loaded result count does not match --expected-count)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.backlog_triage_summary import (
    TriageResult,
    load_results,
)

MANIFEST_VERSION = 1

# Action categories the batch executor knows how to apply or surface.
ACTION_CLOSE = "close"
ACTION_RELABEL = "relabel"
ACTION_PRIORITIZE = "prioritize"
ACTION_DECOMPOSE = "decompose"
ACTION_BATCH = "batch"

# Verdicts from the ai-review action that recommend closing the issue. The
# categorize prompt emits PASS/WARN/etc.; a CLOSE-class verdict marks an issue
# the model judges resolved or invalid.
CLOSE_VERDICTS = frozenset({"CLOSE", "STALE", "INVALID", "DUPLICATE"})


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """One proposed mutation for one issue, before human approval.

    ``category`` is one of the ACTION_* constants. ``labels`` carries the label
    set for a relabel action; ``priority`` carries the target priority for a
    prioritize action; ``rationale`` is the human-facing reason. Fields not
    relevant to the category stay at their defaults.
    """

    issue: int
    category: str
    rationale: str = ""
    labels: tuple[str, ...] = ()
    priority: str = ""

    def to_manifest_entry(self) -> dict[str, object]:
        """Serialize to the manifest wire shape the executor reads."""

        entry: dict[str, object] = {
            "issue": self.issue,
            "category": self.category,
            "rationale": self.rationale,
        }
        if self.labels:
            entry["labels"] = list(self.labels)
        if self.priority:
            entry["priority"] = self.priority
        return entry


def recommend_actions(result: TriageResult) -> list[RecommendedAction]:
    """Derive the recommended actions for one triaged issue.

    Pure function of the result plus the recommendation policy. The same result
    always yields the same actions, so the manifest is reproducible.
    """

    actions: list[RecommendedAction] = []
    _maybe_close(result, actions)
    _maybe_relabel(result, actions)
    _maybe_prioritize(result, actions)
    _maybe_decompose(result, actions)
    _maybe_batch(result, actions)
    return actions


def _maybe_close(result: TriageResult, actions: list[RecommendedAction]) -> None:
    if result.verdict.strip().upper() in CLOSE_VERDICTS:
        actions.append(
            RecommendedAction(
                issue=result.number,
                category=ACTION_CLOSE,
                rationale=f"verdict {result.verdict}",
            )
        )


def _maybe_relabel(result: TriageResult, actions: list[RecommendedAction]) -> None:
    # Area routing maps to agent labels the model suggests for the right worker.
    if not result.area_routing:
        return
    actions.append(
        RecommendedAction(
            issue=result.number,
            category=ACTION_RELABEL,
            rationale="suggested area routing",
            labels=tuple(result.area_routing),
        )
    )


def _maybe_prioritize(result: TriageResult, actions: list[RecommendedAction]) -> None:
    priority = _priority_from_labels(result.labels)
    if not priority:
        return
    actions.append(
        RecommendedAction(
            issue=result.number,
            category=ACTION_PRIORITIZE,
            rationale="priority label suggested",
            priority=priority,
        )
    )


def _maybe_decompose(result: TriageResult, actions: list[RecommendedAction]) -> None:
    scope = result.scope_assessment
    if not scope.needs_decomposition:
        return
    actions.append(
        RecommendedAction(
            issue=result.number,
            category=ACTION_DECOMPOSE,
            rationale=scope.notes or "scope flagged for decomposition",
        )
    )


def _maybe_batch(result: TriageResult, actions: list[RecommendedAction]) -> None:
    scope = result.scope_assessment
    if not scope.can_batch:
        return
    actions.append(
        RecommendedAction(
            issue=result.number,
            category=ACTION_BATCH,
            rationale=scope.notes or "scope flagged as batchable",
        )
    )


def _priority_from_labels(labels: tuple[str, ...]) -> str:
    """Return the first ``priority:PX`` value found in labels, else empty."""

    for label in labels:
        normalized = label.strip()
        if normalized.lower().startswith("priority:"):
            return normalized.split(":", 1)[1].strip()
    return ""


def collect_actions(results: list[TriageResult]) -> list[RecommendedAction]:
    """Flatten the recommended actions across every triaged result."""

    actions: list[RecommendedAction] = []
    for result in results:
        actions.extend(recommend_actions(result))
    return actions


def build_manifest(results: list[TriageResult]) -> dict[str, object]:
    """Build the approval manifest from triaged results.

    The manifest is the contract the executor reads. ``actions`` is a flat list
    so a human can delete the rows they do not approve without restructuring.
    """

    actions = collect_actions(results)
    return {
        "version": MANIFEST_VERSION,
        "approved": False,
        "issues_triaged": len(results),
        "actions": [action.to_manifest_entry() for action in actions],
    }


def render_report(results: list[TriageResult]) -> str:
    """Render the human-review markdown grouping recommendations by category."""

    lines: list[str] = [
        "## Backlog Triage Recommendations",
        "",
        "Proposed actions for the open-issue backlog (issue #2261, part of ",
        "epic #1799). This is a proposal, not an approval. Review each action, ",
        "trim the manifest to the ones you approve, set `approved: true`, then ",
        "run the batch-apply executor. Nothing is applied until you do.",
        "",
    ]
    actions = collect_actions(results)
    if not actions:
        lines.append(f"Issues triaged: {len(results)}. No actions recommended.")
        return "\n".join(lines) + "\n"

    lines.append(f"Issues triaged: {len(results)}. Actions recommended: {len(actions)}.")
    lines.append("")
    by_category = _group_by_category(actions)
    for category in (
        ACTION_CLOSE,
        ACTION_RELABEL,
        ACTION_PRIORITIZE,
        ACTION_DECOMPOSE,
        ACTION_BATCH,
    ):
        entries = by_category.get(category)
        if not entries:
            continue
        lines.extend(_render_category(category, entries))
    return "\n".join(lines) + "\n"


def _group_by_category(
    actions: list[RecommendedAction],
) -> dict[str, list[RecommendedAction]]:
    grouped: dict[str, list[RecommendedAction]] = {}
    for action in actions:
        grouped.setdefault(action.category, []).append(action)
    return grouped


def _render_category(category: str, entries: list[RecommendedAction]) -> list[str]:
    lines = [f"### {category} ({len(entries)})", ""]
    for entry in entries:
        detail = _format_detail(entry)
        rationale = _sanitize(entry.rationale)
        suffix = f" - {rationale}" if rationale else ""
        lines.append(f"- #{entry.issue}{detail}{suffix}")
    lines.append("")
    return lines


def _format_detail(entry: RecommendedAction) -> str:
    if entry.labels:
        return " [" + ", ".join(_sanitize(label) for label in entry.labels) + "]"
    if entry.priority:
        return f" [{_sanitize(entry.priority)}]"
    return ""


def _sanitize(text: str) -> str:
    """Collapse newlines so a value stays on one markdown list line."""

    return text.replace("\n", " ").replace("\r", " ").strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate AI-triage results into a recommendation report and manifest.",
    )
    parser.add_argument(
        "--results-dir", required=True,
        help="Directory holding per-issue triage result JSON files.",
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to write the JSON approval manifest.",
    )
    parser.add_argument(
        "--report", required=True,
        help="Path to write the markdown recommendation report.",
    )
    parser.add_argument(
        "--github-step-summary",
        default="",
        help="Optional GitHub step summary file to append the markdown report to.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=-1,
        help="Expected number of result JSON files. Negative disables count validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    if results_dir.is_dir():
        results = load_results(results_dir)
    else:
        # Missing artifacts (every matrix job failed) yields an empty manifest so
        # the report job still produces a reviewable artifact.
        results = []
    manifest = build_manifest(results)
    report = render_report(results)

    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    Path(args.report).write_text(report, encoding="utf-8")
    if args.github_step_summary:
        with Path(args.github_step_summary).open("a", encoding="utf-8") as handle:
            handle.write(report)
    print(f"Wrote recommendation manifest to {args.manifest}")
    print(f"Wrote recommendation report to {args.report}")

    if args.expected_count >= 0 and len(results) != args.expected_count:
        print(
            f"Loaded {len(results)} triage results, expected {args.expected_count}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
