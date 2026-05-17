#!/usr/bin/env python3
"""Post-eval hook: turn eval pass/fail outcomes into skillbook evidence.

This is NOT a harness lifecycle hook (it is not one of the SessionStart /
PreToolUse / PostToolUse / Stop / PreCompact events in hooks.yaml). It is a
script invoked by the eval pipeline after an agent-vs-baseline run completes.
It is the anti-corruption layer between the eval corpus and the skillbook:
it reads raw eval outcomes and translates them into confirm / contradict
operations on the policies the evals are tagged with.

Linkage:
  - An eval fixture (evals/<spike>/fixtures/F*.json) is tagged with a
    "policy_id" field naming the policy it exercises.
  - A run produces evals/<spike>/runs/<RUN_ID>/runs.jsonl, one JSON record
    per trial with at least "fixture_id" and "passed".

For each tagged fixture this hook aggregates its trials (the fixture passes
when a strict majority of its trials passed), then logs eval-grounded
evidence: a passing fixture confirms its policy, a failing fixture
contradicts it. After logging evidence it runs the promotion pass so tiers
and statuses reflect the new evidence.

Idempotency: evidence is keyed on "<RUN_ID>::<fixture_id>", where RUN_ID is
the canonical eval run identifier (the run directory name, e.g.
20260503T182553Z-eaa08f8d). Re-processing the same run directory is a
no-op. A genuinely new eval run produces a new run directory and is
correctly counted as new evidence. Do not pass --run-id to relabel an
already-processed run; that defeats the dedupe key.

Usage:
  post-eval.py --run <evals/<spike>/runs/<RUN_ID>> --fixtures <fixtures-dir>

EXIT CODES (ADR-035):
  0  - Success: evidence applied (or nothing to apply)
  1  - Logic error: malformed run records
  2  - Config error: run or fixtures path missing

See: .agents/skillbook/README.md and ADR-035.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.skillbook import (  # noqa: E402
    add_evidence,
    find_policy,
    load_skillbook_file,
    make_evidence_entry,
    run_promote,
    save_skillbook_file,
    skillbook_paths,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


def aggregate_fixture_outcomes(runs_jsonl: Path) -> dict[str, bool]:
    """Read a runs.jsonl file and return {fixture_id: passed} per fixture.

    A fixture passes when a strict majority of its trial records passed.
    """
    passed_counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for line in runs_jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        fixture_id = record.get("fixture_id")
        if not fixture_id:
            raise ValueError(f"run record missing fixture_id: {line}")
        total_counts[fixture_id] = total_counts.get(fixture_id, 0) + 1
        if bool(record.get("passed")):
            passed_counts[fixture_id] = passed_counts.get(fixture_id, 0) + 1
    return {
        fixture_id: passed_counts.get(fixture_id, 0) * 2 > total
        for fixture_id, total in total_counts.items()
    }


def fixture_policy_id(fixtures_dir: Path, fixture_id: str) -> str | None:
    """Return the policy_id a fixture is tagged with, or None if untagged/missing."""
    fixture_path = fixtures_dir / f"{fixture_id}.json"
    if not fixture_path.exists():
        return None
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return fixture.get("policy_id")


def apply_eval_run(
    runs_jsonl: Path,
    fixtures_dir: Path,
    skillbook_dir: Path,
    run_id: str,
    now: int,
) -> dict[str, Any]:
    """Apply one eval run's outcomes to the skillbook. Return a summary dict.

    For each tagged fixture, append confirm/contradict evidence to its policy,
    then run the promotion pass. Idempotent: evidence is keyed on the run id
    plus fixture id.
    """
    outcomes = aggregate_fixture_outcomes(runs_jsonl)
    paths = skillbook_paths(skillbook_dir)
    data = load_skillbook_file(paths["policies"])

    summary: dict[str, Any] = {
        "run_id": run_id,
        "confirmed": [],
        "contradicted": [],
        "skipped_untagged": [],
        "skipped_unknown_policy": [],
    }
    for fixture_id, passed in sorted(outcomes.items()):
        policy_id = fixture_policy_id(fixtures_dir, fixture_id)
        if policy_id is None:
            summary["skipped_untagged"].append(fixture_id)
            continue
        policy = find_policy(data, policy_id)
        if policy is None:
            summary["skipped_unknown_policy"].append(f"{fixture_id}:{policy_id}")
            continue
        evidence_type = "confirmed" if passed else "contradicted"
        entry = make_evidence_entry(
            evidence_type=evidence_type,
            eval_id=f"{run_id}::{fixture_id}",
            context_type="external",
            ts=now,
            reason=None if passed else f"eval fixture {fixture_id} failed",
        )
        if add_evidence(policy, entry):
            bucket = "confirmed" if passed else "contradicted"
            summary[bucket].append(policy_id)

    summary["promoted"] = run_promote(data, now)
    save_skillbook_file(paths["policies"], data)
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    """Print a human-readable summary of an apply_eval_run result."""
    print(f"post-eval: run {summary['run_id']}")
    print(f"  confirmed:   {len(summary['confirmed'])} policy(ies)")
    print(f"  contradicted: {len(summary['contradicted'])} policy(ies)")
    print(f"  promoted/updated: {len(summary['promoted'])} policy(ies)")
    if summary["skipped_untagged"]:
        print(f"  skipped (no policy_id): {', '.join(summary['skipped_untagged'])}")
    if summary["skipped_unknown_policy"]:
        print(
            f"  skipped (unknown policy): "
            f"{', '.join(summary['skipped_unknown_policy'])}"
        )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and apply an eval run's outcomes to the skillbook."""
    parser = argparse.ArgumentParser(
        description="Apply eval pass/fail outcomes to skillbook policies."
    )
    parser.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Eval run directory containing runs.jsonl (its name is the run id).",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Directory of eval fixture JSON files (tagged with policy_id).",
    )
    parser.add_argument(
        "--skillbook-dir",
        type=Path,
        default=_PROJECT_ROOT / ".agents" / "skillbook",
        help="Directory holding the skillbook JSON files.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the run id (defaults to the --run directory name).",
    )
    args = parser.parse_args(argv)

    runs_jsonl = args.run / "runs.jsonl"
    if not runs_jsonl.exists():
        print(f"Error: runs.jsonl not found in {args.run}", file=sys.stderr)
        return EXIT_CONFIG
    if not args.fixtures.is_dir():
        print(f"Error: fixtures directory not found: {args.fixtures}", file=sys.stderr)
        return EXIT_CONFIG

    run_id = args.run_id or args.run.name
    try:
        summary = apply_eval_run(
            runs_jsonl, args.fixtures, args.skillbook_dir, run_id, int(time.time())
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Error: malformed eval data: {exc}", file=sys.stderr)
        return EXIT_LOGIC

    _print_summary(summary)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
