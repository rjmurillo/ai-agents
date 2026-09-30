#!/usr/bin/env python3
"""Report per-artifact evidence states for rules and skills (issue #4882).

`check_rule_activation_coverage.py` ratchets baseline membership. Membership
is a non-regression inventory, never proof that an always-loaded rule earns its
context cost. This report keeps the states apart so a consumer (issue #4871)
cannot read one as another:

  baseline_exempt              no scenario; only the baseline allows it.
  scenario_defined_not_scored  a well-formed scenario exists. The artifact can
                               be measured; nothing says it was.
  not_baselined                no scenario and not baselined. The ratchet gate
                               fails on these; listed so none drops out.
  scored                       always null here. Scored efficacy needs a live
                               run of `scripts/eval/eval-rule-activation.py`.

Exit codes: 0 report written, 2 config or structural error (the same
conditions the coverage gate refuses).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))
from check_rule_activation_coverage import (  # noqa: E402
    DEFAULT_BASELINE_NAME,
    CoverageConfigError,
    covered_ids,
    discover_rules,
    discover_skills,
    load_baseline,
)

SCORED_SOURCE = "scripts/eval/eval-rule-activation.py"

EXIT_OK = 0
EXIT_CONFIG = 2


def coverage_states(repo_root: Path, baseline_path: Path) -> dict[str, Any]:
    """Classify every rule and skill into an evidence state."""
    base_rules, base_skills = load_baseline(baseline_path)
    payload: dict[str, Any] = {"scored": None, "scored_source": SCORED_SOURCE}
    for kind, universe, covered, base in (
        ("rules", discover_rules(repo_root), covered_ids(repo_root, "rule"), base_rules),
        ("skills", discover_skills(repo_root), covered_ids(repo_root, "skill"), base_skills),
    ):
        uncovered = universe - covered
        payload[kind] = {
            "baseline_exempt": sorted(uncovered & base),
            "not_baselined": sorted(uncovered - base),
            "scenario_defined_not_scored": sorted(universe & covered),
        }
    return payload


def write_report(path: Path, payload: dict[str, Any]) -> None:
    """Write the report as JSON, failing closed on I/O errors."""
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CoverageConfigError(f"cannot write report {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True, help="JSON report path.")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    baseline = args.baseline or repo_root / "scripts" / "validation" / DEFAULT_BASELINE_NAME
    try:
        write_report(args.output, coverage_states(repo_root, baseline))
    except CoverageConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(f"Report written: {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
