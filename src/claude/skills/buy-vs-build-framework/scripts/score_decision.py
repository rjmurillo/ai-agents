#!/usr/bin/env python3
"""
Calculate weighted decision scores with sensitivity analysis.

Exit codes:
  0: Clear winner (>20% score gap)
  1: Tie requires human judgment (scores within 10%)
"""

import argparse
import json
import sys
from dataclasses import dataclass


@dataclass
class DecisionScore:
    """Structured result for decision scoring."""
    scores: dict[str, float]
    winner: str
    confidence: str
    sensitivity: dict[str, float]


def validate_criteria(criteria: dict) -> list[str]:
    """Validate criteria structure and weights."""
    errors = []

    if 'weights' not in criteria:
        errors.append("Missing 'weights' section in criteria file")
        return errors

    total_weight = sum(criteria['weights'].values())
    if abs(total_weight - 100.0) > 0.01:
        errors.append(f"Weights must sum to 100%, got {total_weight}%")

    if 'options' not in criteria:
        errors.append("Missing 'options' section in criteria file")
        return errors

    for option in criteria['options'].values():
        for category in criteria['weights'].keys():
            if category not in option:
                errors.append(f"Option missing category: {category}")

    return errors


def calculate_scores(criteria: dict) -> dict[str, float]:
    """Calculate weighted scores for each option."""
    scores = {}

    for option_name, option_scores in criteria['options'].items():
        total_score = 0.0
        for category, weight in criteria['weights'].items():
            category_score = sum(option_scores[category].values()) / len(option_scores[category])
            total_score += category_score * (weight / 100.0)
        scores[option_name] = total_score

    return scores


def determine_confidence(scores: dict[str, float]) -> str:
    """Determine confidence based on score gap."""
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) < 2:
        return "high"

    gap = (sorted_scores[0] - sorted_scores[1]) / sorted_scores[0] * 100

    if gap > 20:
        return "high"
    elif gap > 10:
        return "medium"
    else:
        return "low"


def sensitivity_analysis(criteria: dict, base_scores: dict[str, float]) -> dict[str, float]:
    """Analyze how weight changes affect ranking."""
    sensitivity = {}

    for category in criteria['weights'].keys():
        # Test ±20% weight change
        test_criteria = json.loads(json.dumps(criteria))  # Deep copy
        original_weight = test_criteria['weights'][category]

        # Redistribute weight proportionally
        test_criteria['weights'][category] = original_weight * 1.2
        remaining = 100 - test_criteria['weights'][category]

        for other_category in test_criteria['weights'].keys():
            if other_category != category:
                proportion = test_criteria['weights'][other_category] / (100 - original_weight)
                test_criteria['weights'][other_category] = remaining * proportion

        new_scores = calculate_scores(test_criteria)
        max_delta = max(abs(new_scores[opt] - base_scores[opt]) for opt in base_scores.keys())
        sensitivity[category] = max_delta

    return sensitivity


def main():
    parser = argparse.ArgumentParser(
        description="Calculate weighted decision scores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example criteria file format (JSON):
{
  "weights": {
    "strategic": 40.0,
    "operational": 30.0,
    "risk": 30.0
  },
  "options": {
    "build": {
      "strategic": {"alignment": 9, "optionality": 8, "upside": 9},
      "operational": {"time_to_value": 5, "team_fit": 8, "integration": 7},
      "risk": {"vendor": 10, "execution": 6, "regulatory": 8}
    },
    "buy": { ... },
    "partner": { ... }
  }
}
        """
    )

    parser.add_argument('--criteria-file', type=str, required=True,
                       help='JSON file with criteria weights and scores')

    args = parser.parse_args()

    # Load criteria
    # Validate input path to prevent path traversal (CWE-22)
    import os
    try:
        allowed_base = os.path.abspath(".")
        criteria_file_path = os.path.abspath(args.criteria_file)
        if not criteria_file_path.startswith(allowed_base):
            raise ValueError(
                f"Path traversal attempt detected in --criteria-file: "
                f"{args.criteria_file}"
            )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Load criteria
    try:
        with open(criteria_file_path) as f:
            criteria = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Criteria file not found: {args.criteria_file}", file=sys.stderr)
        sys.exit(11)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in criteria file: {e}", file=sys.stderr)
        sys.exit(11)

    # Validate criteria
    errors = validate_criteria(criteria)
    if errors:
        print("ERROR: Validation failed", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(11)

    # Calculate scores
    scores = calculate_scores(criteria)
    winner = max(scores, key=scores.get)
    confidence = determine_confidence(scores)

    # Sensitivity analysis
    sensitivity = sensitivity_analysis(criteria, scores)

    # Output results
    print("Decision Matrix Scores")
    print(f"{'='*60}")
    for option, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        print(f"{option.capitalize():12} {score:.1f}")
    print("")
    print(f"Winner:     {winner.capitalize()}")
    print(f"Confidence: {confidence.upper()}")
    print("")
    print("Sensitivity Analysis (±20% weight)")
    for category, delta in sorted(sensitivity.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category:12} ±{delta:.1f} points")

    # Determine exit code
    if confidence == "low":
        print("\nNOTE: Low confidence (scores within 10%) - human judgment required")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
