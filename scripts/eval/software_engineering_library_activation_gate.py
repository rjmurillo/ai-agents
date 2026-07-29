#!/usr/bin/env python3
"""Persist rollback-trigger state for software-engineering-library activation evals.

The live eval script measures whether each moved book reference remains reachable
through the progressive-disclosure skill route. This gate stores consecutive
activation failures across scheduled runs so ADR-088 has an enforceable rollback
trigger instead of prose-only intent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MOVED_REFERENCE_IDS = (
    "clean-architecture",
    "domain-driven-design",
    "enterprise-patterns",
    "refactoring",
    "release-it",
    "philosophy-of-software-design",
    "data-intensive-applications",
    "working-with-legacy-code",
)

OWNER = "agent-qa"
CADENCE = "weekly Monday 06:30 UTC and pull_request dry-run gate"
DEFAULT_THRESHOLD = 2
ROLLBACK_VERDICTS = {"FAIL_THRESHOLD", "FAIL_NO_DELTA", "NO_POSITIVE_CASES", "NO_RESULT"}
EXTERNAL_VERDICTS = {"FAIL_JUDGE_ERRORS"}
RESTORATION_PR_POLICY = (
    "When any moved reference reaches the consecutive activation failure "
    "threshold, the scheduled workflow fails and opens or updates the rollback "
    "tracking issue. agent-qa owns the next restoration PR, which must restore "
    "the failing book reference to the always-on rule surface or strengthen the "
    "skill trigger and include this gate's report. The workflow blocks merge for "
    "any PR that touches the skill, scenarios, or gate while the threshold still "
    "fails."
)


def _empty_reference_state() -> dict[str, Any]:
    return {
        "consecutive_activation_failures": 0,
        "last_verdict": "UNKNOWN",
        "last_result_counted_for_rollback": False,
        "last_run_id": None,
        "last_checked_at": None,
    }


def _base_state(existing: dict[str, Any] | None, threshold: int) -> dict[str, Any]:
    state = dict(existing or {})
    state["schema_version"] = 1
    state["owner"] = OWNER
    state["cadence"] = CADENCE
    state["rollback_threshold"] = threshold
    state["restoration_pr_policy"] = RESTORATION_PR_POLICY
    references = state.get("references")
    state["references"] = references if isinstance(references, dict) else {}
    return state


def _verdict_for(results: dict[str, Any], reference_id: str) -> str:
    rule = results.get("rules", {}).get(reference_id)
    if not isinstance(rule, dict):
        return "NO_RESULT"
    summary = rule.get("summary")
    if not isinstance(summary, dict):
        return "NO_RESULT"
    verdict = summary.get("verdict")
    return verdict if isinstance(verdict, str) and verdict else "NO_RESULT"


def _update_reference(
    previous: dict[str, Any], verdict: str, run_id: str, checked_at: str
) -> dict[str, Any]:
    current = _empty_reference_state() | previous
    counted = verdict in ROLLBACK_VERDICTS
    if verdict == "PASS":
        streak = 0
    elif counted:
        streak = int(current.get("consecutive_activation_failures", 0)) + 1
    else:
        streak = int(current.get("consecutive_activation_failures", 0))
    current.update(
        {
            "consecutive_activation_failures": streak,
            "last_verdict": verdict,
            "last_result_counted_for_rollback": counted,
            "last_run_id": run_id,
            "last_checked_at": checked_at,
        }
    )
    if verdict in EXTERNAL_VERDICTS:
        current["last_external_failure_at"] = checked_at
    return current


def update_state(
    existing: dict[str, Any] | None,
    results: dict[str, Any],
    *,
    run_id: str,
    checked_at: str,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Return updated persistent state for all ADR-088 moved references."""
    state = _base_state(existing, threshold)
    references = state["references"]
    for reference_id in MOVED_REFERENCE_IDS:
        previous = references.get(reference_id, {})
        if not isinstance(previous, dict):
            previous = {}
        references[reference_id] = _update_reference(
            previous, _verdict_for(results, reference_id), run_id, checked_at
        )
    state["last_run_id"] = run_id
    state["last_checked_at"] = checked_at
    return state


def evaluate_thresholds(state: dict[str, Any], threshold: int) -> dict[str, Any]:
    """Report references whose consecutive activation failures reached threshold."""
    references = state.get("references", {})
    at_threshold = []
    for reference_id in MOVED_REFERENCE_IDS:
        ref_state = references.get(reference_id, {})
        streak = int(ref_state.get("consecutive_activation_failures", 0))
        if streak >= threshold:
            at_threshold.append(reference_id)
    return {
        "threshold": threshold,
        "threshold_exceeded": bool(at_threshold),
        "references_at_threshold": at_threshold,
        "owner": OWNER,
        "cadence": CADENCE,
        "restoration_pr_policy": RESTORATION_PR_POLICY,
    }


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is not None:
            return dict(default)
        raise ValueError(f"JSON file not found: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return parsed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_report(state: dict[str, Any], report: dict[str, Any]) -> str:
    lines = [
        "# Software Engineering Library Activation Gate",
        "",
        f"Owner: `{OWNER}`",
        f"Cadence: {CADENCE}",
        f"Threshold: {report['threshold']} consecutive activation failures",
        "",
        "| Reference | Verdict | Consecutive activation failures | Counts for rollback |",
        "|-----------|---------|----------------------------------|---------------------|",
    ]
    for reference_id in MOVED_REFERENCE_IDS:
        ref_state = state["references"][reference_id]
        lines.append(
            "| "
            f"{reference_id} | {ref_state['last_verdict']} | "
            f"{ref_state['consecutive_activation_failures']} | "
            f"{ref_state['last_result_counted_for_rollback']} |"
        )
    if report["threshold_exceeded"]:
        refs = ", ".join(report["references_at_threshold"])
        lines.extend(["", f"ROLLBACK THRESHOLD EXCEEDED: {refs}"])
    else:
        lines.extend(["", "Rollback threshold not exceeded."])
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, help="eval-rule-activation JSON output")
    parser.add_argument("--state", required=True, help="previous persistent state JSON")
    parser.add_argument("--output-state", required=True, help="updated persistent state JSON")
    parser.add_argument("--report", help="write markdown gate report")
    parser.add_argument("--threshold-report", help="write threshold report JSON")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    parser.add_argument("--checked-at", default=datetime.now(UTC).isoformat())
    parser.add_argument("--fail-on-threshold", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results = load_json(Path(args.results))
        previous = load_json(Path(args.state), default={})
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    state = update_state(
        previous,
        results,
        run_id=args.run_id,
        checked_at=args.checked_at,
        threshold=args.threshold,
    )
    report = evaluate_thresholds(state, args.threshold)
    write_json(Path(args.output_state), state)
    if args.threshold_report:
        write_json(Path(args.threshold_report), report)
    rendered = render_report(state, report)
    if args.report:
        Path(args.report).write_text(rendered, encoding="utf-8")
    print(rendered)
    if args.fail_on_threshold and report["threshold_exceeded"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
