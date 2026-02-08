#!/usr/bin/env python3
"""
Detect assumption drift and recommend re-evaluation.

Exit codes:
  0: Assumptions hold, stay course
  1: Error (file not found or invalid JSON)
  2: Minor drift (<20%), monitor closely
  3: Major drift (>20%), re-evaluation required
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass


@dataclass
class DriftAnalysis:
    """Structured result for drift analysis."""
    drift_analysis: dict[str, float]
    recommendation: str
    triggered_rules: list[str]


def parse_adr(adr_path: str) -> dict:
    """Extract assumptions from ADR markdown."""
    try:
        with open(adr_path) as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: ADR file not found: {adr_path}", file=sys.stderr)
        sys.exit(1)

    assumptions = {}

    # Extract decision type (Build/Buy/Partner/Defer)
    decision_match = re.search(r'##\s+Decision\s+We will (BUILD|BUY|PARTNER|DEFER)', content, re.IGNORECASE)
    if decision_match:
        assumptions['decision_type'] = decision_match.group(1).lower()

    # Extract TCO figures if present
    tco_matches = re.findall(r'\$([0-9,]+)', content)
    if tco_matches:
        assumptions['costs'] = [int(m.replace(',', '')) for m in tco_matches]

    # Extract time horizon
    horizon_match = re.search(r'(\d+)\s*year', content, re.IGNORECASE)
    if horizon_match:
        assumptions['time_horizon_years'] = int(horizon_match.group(1))

    return assumptions


def calculate_drift(original: dict, current: dict) -> dict[str, float]:
    """Calculate drift percentage for each assumption."""
    drift = {}

    # Cost drift
    if 'costs' in original and 'costs' in current:
        orig_total = sum(original['costs'])
        curr_total = sum(current['costs'])
        if orig_total > 0:
            drift['cost'] = abs(curr_total - orig_total) / orig_total * 100

    # Time horizon drift
    if 'time_horizon_years' in original and 'time_horizon_years' in current:
        orig_horizon = original['time_horizon_years']
        curr_horizon = current['time_horizon_years']
        if orig_horizon > 0:
            drift['time_horizon'] = abs(curr_horizon - orig_horizon) / orig_horizon * 100

    # Strategic priority drift (from current state only)
    if 'strategic_priority_changed' in current:
        drift['strategic_priority'] = 100 if current['strategic_priority_changed'] else 0

    # Vendor viability (from current state only)
    if 'vendor_viability_concerns' in current:
        drift['vendor_viability'] = 100 if current['vendor_viability_concerns'] else 0

    # Team capacity (from current state only)
    if 'team_capacity_changed' in current:
        drift['team_capacity'] = 100 if current['team_capacity_changed'] else 0

    return drift


def check_triggers(drift: dict[str, float], current: dict) -> list[str]:
    """Check which reassessment triggers have fired."""
    triggered = []

    if 'cost' in drift and drift['cost'] > 20:
        triggered.append(f"Cost assumption changed {drift['cost']:.1f}% (trigger: >20%)")

    if 'time_horizon' in drift and drift['time_horizon'] > 20:
        triggered.append(f"Time horizon shifted {drift['time_horizon']:.1f}% (trigger: material shift)")

    if 'strategic_priority' in drift and drift['strategic_priority'] > 0:
        triggered.append("Strategic priority shifted (core <-> context)")

    if 'vendor_viability' in drift and drift['vendor_viability'] > 0:
        triggered.append("Vendor viability concerns detected (M&A, financials, EOL)")

    if 'team_capacity' in drift and drift['team_capacity'] > 0:
        triggered.append("Team capacity changed (key departures or hiring surge)")

    if current.get('competitive_dynamics_shifted', False):
        triggered.append("Competitive dynamics shifted (urgency increased)")

    if current.get('regulatory_changes', False):
        triggered.append("Regulatory changes affect decision")

    if current.get('technology_disruption', False):
        triggered.append("Technology disruption makes decision obsolete")

    if current.get('customer_demand_signal', False):
        triggered.append("Customer demand signal changed")

    return triggered


def determine_recommendation(drift: dict[str, float], triggered: list[str]) -> tuple[str, int]:
    """Determine recommendation and exit code."""
    max_drift = max(drift.values()) if drift else 0

    if len(triggered) >= 3 or max_drift > 20:
        return ("Full re-evaluation required", 3)
    elif len(triggered) >= 1 or max_drift > 10:
        return ("Monitor closely, consider re-evaluation", 2)
    else:
        return ("Assumptions hold, stay course", 0)


def main():
    parser = argparse.ArgumentParser(
        description="Detect assumption drift and recommend re-evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example current state file format (JSON):
{
  "costs": [600000, 120000],
  "time_horizon_years": 3,
  "strategic_priority_changed": false,
  "vendor_viability_concerns": true,
  "team_capacity_changed": false,
  "competitive_dynamics_shifted": false,
  "regulatory_changes": false,
  "technology_disruption": false,
  "customer_demand_signal": false
}
        """
    )

    parser.add_argument('--adr-file', type=str, required=True,
                       help='ADR markdown file with original assumptions')
    parser.add_argument('--current-state', type=str, required=True,
                       help='JSON file with current state')

    args = parser.parse_args()

    # Parse ADR for original assumptions
    original = parse_adr(args.adr_file)

    # Load current state
    try:
        with open(args.current_state) as f:
            current = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Current state file not found: {args.current_state}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in current state file: {e}", file=sys.stderr)
        sys.exit(1)

    # Calculate drift
    drift = calculate_drift(original, current)

    # Check triggers
    triggered = check_triggers(drift, current)

    # Determine recommendation
    recommendation, exit_code = determine_recommendation(drift, triggered)

    # Output results
    print("Reassessment Trigger Analysis")
    print(f"{'='*60}")
    print(f"Original Decision: {original.get('decision_type', 'Unknown').upper()}")
    print("")
    print("Drift Analysis:")
    for key, value in sorted(drift.items(), key=lambda x: x[1], reverse=True):
        print(f"  {key:20} {value:.1f}%")
    print("")
    print(f"Triggered Rules ({len(triggered)}):")
    for rule in triggered:
        print(f"  - {rule}")
    print("")
    print(f"Recommendation: {recommendation}")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
