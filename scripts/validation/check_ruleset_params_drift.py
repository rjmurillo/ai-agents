#!/usr/bin/env python3
"""Check recorded ruleset parameters against the live GitHub API.

Compares the values in ruleset_params_baseline.json against the live
ruleset fetched via `gh api`. Exits non-zero when any parameter drifts.

Usage (local):
    python scripts/validation/check_ruleset_params_drift.py

Usage (CI, offline / no token):
    python scripts/validation/check_ruleset_params_drift.py --offline

EXIT CODES (ADR-035):
    0 - all parameters match or --offline skipped the live check
    1 - drift detected
    2 - configuration error (missing baseline, bad JSON)
    3 - external error (gh CLI unavailable, API failure)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

BASELINE_PATH = Path(__file__).parent / "ruleset_params_baseline.json"
REPO = "rjmurillo/ai-agents"


def load_baseline() -> dict[str, Any]:
    """Load the expected parameter baseline."""
    if not BASELINE_PATH.exists():
        print(f"ERROR: baseline not found: {BASELINE_PATH}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    try:
        result: dict[str, Any] = json.loads(
            BASELINE_PATH.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in baseline: {exc}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    if "parameters" not in result:
        print("ERROR: baseline missing 'parameters' key", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    return result


def fetch_live_params(ruleset_id: int) -> dict[str, Any]:
    """Fetch live ruleset parameters from GitHub API via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/rulesets/{ruleset_id}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: gh CLI not found on PATH", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        exit_code = EXIT_AUTH if "auth" in stderr.lower() else EXIT_EXTERNAL
        print(
            f"ERROR: gh api failed (exit {result.returncode}): {stderr}",
            file=sys.stderr,
        )
        sys.exit(exit_code)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON from API: {exc}", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)

    params: dict[str, Any] = {}
    for rule in data.get("rules", []):
        rule_params = rule.get("parameters", {})
        if rule_params:
            params.update(rule_params)
    return params


def check_drift(
    baseline: dict[str, Any], live: dict[str, Any]
) -> list[str]:
    """Compare baseline parameters against live values. Return drift messages."""
    drifts: list[str] = []
    baseline_params = baseline.get("parameters", {})
    for key, expected in baseline_params.items():
        actual = live.get(key)
        if actual is None:
            drifts.append(
                f"  {key}: expected={expected!r}, not found in live ruleset"
            )
        elif actual != expected:
            drifts.append(f"  {key}: expected={expected!r}, actual={actual!r}")
    # Detect parameters present live but absent from baseline
    for key in live:
        if key not in baseline_params:
            drifts.append(
                f"  {key}: unexpected parameter (not in baseline), value={live[key]!r}"
            )
    return drifts


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = argv if argv is not None else sys.argv[1:]

    if "--offline" in args:
        print("SKIP: --offline flag set, no live check performed.")
        return EXIT_OK

    baseline = load_baseline()
    ruleset_id = baseline.get("ruleset_id")
    if not ruleset_id:
        print("ERROR: ruleset_id missing from baseline", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    live = fetch_live_params(ruleset_id)
    drifts = check_drift(baseline, live)

    if drifts:
        print("DRIFT DETECTED between baseline and live ruleset:")
        print("\n".join(drifts))
        print(
            f"\nUpdate {BASELINE_PATH.name} after confirming the change is"
            " intentional."
        )
        return EXIT_DRIFT

    print("OK: all recorded ruleset parameters match live values.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
