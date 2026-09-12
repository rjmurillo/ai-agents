#!/usr/bin/env python3
"""Check recorded ruleset state against the live GitHub API.

Compares ruleset_params_baseline.json against the live ruleset fetched via
`gh api`, in both directions:

  * every baseline parameter's value against its live value (and detects a
    baseline parameter that disappeared from the live rule set)
  * every live parameter key that has no baseline entry (unknown-key drift,
    so an added rule or a widened permission cannot go unnoticed)
  * the ruleset's top-level `enforcement` and `bypass_actors` state, which
    live outside any rule's `parameters` block and were previously never
    fetched at all

Exits non-zero when any of the above drifts.

Usage (local):
    python scripts/validation/check_ruleset_params_drift.py

Usage (CI, offline / no token):
    python scripts/validation/check_ruleset_params_drift.py --offline

EXIT CODES (ADR-035):
    0 - all state matches or --offline skipped the live check
    1 - drift detected
    2 - configuration error (missing baseline, bad JSON, missing/malformed
        'parameters' or 'ruleset' section)
    3 - external error (gh CLI unavailable, API failure)
    4 - authentication error (gh CLI not authenticated)
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

# `required_status_checks` is both a rule TYPE and, within that rule's
# `parameters` block, a parameter KEY holding the list of required status
# check contexts. That key is owned by
# scripts/ci/ruleset_required_contexts.py (module-level REQUIRED_CONTEXTS),
# which scripts/ci/ruleset_context_drift.py already compares against the
# live ruleset. Per the decision recorded in
# .serena/memories/decision-ruleset-drift-must-not-create-a-second-baseline.md,
# no second baseline of the required contexts may exist, so this module
# excludes the key from both value comparison and unknown-key detection.
DELEGATED_PARAM_KEYS: frozenset[str] = frozenset({"required_status_checks"})


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
    ruleset_state = result.get("ruleset")
    if not isinstance(ruleset_state, dict):
        print("ERROR: baseline missing 'ruleset' key", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    if "enforcement" not in ruleset_state or "bypass_actors" not in ruleset_state:
        print(
            "ERROR: baseline 'ruleset' section missing 'enforcement' or"
            " 'bypass_actors'",
            file=sys.stderr,
        )
        sys.exit(EXIT_CONFIG)
    return result


def fetch_live_ruleset(ruleset_id: int) -> dict[str, Any]:
    """Fetch the full live ruleset payload from GitHub API via gh CLI.

    Returns the raw decoded JSON object exactly as `gh api
    repos/<repo>/rulesets/<id>` produces it, so callers can read both
    per-rule `parameters` (see extract_live_params) and top-level ruleset
    state such as `enforcement` and `bypass_actors` (see
    extract_live_ruleset_state) from a single API call.
    """
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
        data: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON from API: {exc}", file=sys.stderr)
        sys.exit(EXIT_EXTERNAL)

    return data


def extract_live_params(data: dict[str, Any]) -> dict[str, Any]:
    """Union rule-level `parameters` across every rule in the ruleset payload."""
    params: dict[str, Any] = {}
    for rule in data.get("rules", []):
        rule_params = rule.get("parameters", {})
        if rule_params:
            params.update(rule_params)
    return params


def extract_live_ruleset_state(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the ruleset's top-level `enforcement` and `bypass_actors`."""
    return {
        "enforcement": data.get("enforcement"),
        "bypass_actors": data.get("bypass_actors", []),
    }


def check_drift(
    baseline: dict[str, Any], live: dict[str, Any]
) -> list[str]:
    """Compare baseline parameters against live values. Return drift messages.

    Bidirectional: reports a baseline value that no longer matches live (or
    disappeared from it), AND a live parameter key with no baseline entry
    (unknown-key drift), so a widened permission is caught even though it was
    never baselined. DELEGATED_PARAM_KEYS is excluded from both directions;
    see its module-level comment for why.
    """
    drifts: list[str] = []
    baseline_params = baseline.get("parameters", {})

    for key, expected in baseline_params.items():
        if key in DELEGATED_PARAM_KEYS:
            continue
        actual = live.get(key)
        if actual is None:
            drifts.append(
                f"  {key}: expected={expected!r}, not found in live ruleset"
            )
        elif actual != expected:
            drifts.append(f"  {key}: expected={expected!r}, actual={actual!r}")

    for key, actual in live.items():
        if key in baseline_params or key in DELEGATED_PARAM_KEYS:
            continue
        drifts.append(
            f"  {key}: unrecognized live parameter (value={actual!r}),"
            " not present in baseline"
        )

    return drifts


def _bypass_actor_sort_key(actor: dict[str, Any]) -> tuple[str, ...]:
    """Stable sort key for one bypass actor dict.

    Every component is stringified so a heterogeneous list (an actor missing
    a field, or a future actor type whose actor_id is not an int) sorts
    instead of raising TypeError. Ordering only has to be stable here, not
    semantically meaningful: it exists so list reordering is not read as
    drift, and equality is still compared on the original dicts.
    """
    return (
        str(actor.get("actor_id")),
        str(actor.get("actor_type")),
        str(actor.get("bypass_mode")),
    )


def _normalize_bypass_actors(actors: list[Any]) -> list[Any]:
    """Sort bypass actors so list reordering is not read as drift."""
    return sorted(actors, key=_bypass_actor_sort_key)


def check_ruleset_drift(
    baseline: dict[str, Any], live_ruleset: dict[str, Any]
) -> list[str]:
    """Compare baseline top-level ruleset state against live state.

    `live_ruleset` is the shape extract_live_ruleset_state returns:
    {"enforcement": ..., "bypass_actors": [...]}. `bypass_actors` is compared
    order-insensitively (GitHub may return the list in a different order
    without any actor having changed), but an added, removed, or modified
    actor is still reported.
    """
    drifts: list[str] = []
    baseline_ruleset = baseline.get("ruleset", {})

    expected_enforcement = baseline_ruleset.get("enforcement")
    actual_enforcement = live_ruleset.get("enforcement")
    if actual_enforcement != expected_enforcement:
        drifts.append(
            f"  enforcement: expected={expected_enforcement!r},"
            f" actual={actual_enforcement!r}"
        )

    expected_actors = _normalize_bypass_actors(
        baseline_ruleset.get("bypass_actors", [])
    )
    actual_actors = _normalize_bypass_actors(live_ruleset.get("bypass_actors", []))
    if actual_actors != expected_actors:
        drifts.append(
            f"  bypass_actors: expected={expected_actors!r},"
            f" actual={actual_actors!r}"
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

    data = fetch_live_ruleset(ruleset_id)
    live_params = extract_live_params(data)
    live_ruleset_state = extract_live_ruleset_state(data)

    drifts = check_drift(baseline, live_params)
    drifts += check_ruleset_drift(baseline, live_ruleset_state)

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
