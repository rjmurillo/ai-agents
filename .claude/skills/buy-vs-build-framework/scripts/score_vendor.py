#!/usr/bin/env python3
"""
Score vendor stability, pricing, feature fit, and support quality.

Exit codes:
  0: Pass (score >70)
  10: Yellow flag (score 50-70)
  11: Red flag (score <50)
"""

import argparse
import json
import sys
from dataclasses import dataclass


@dataclass
class VendorScore:
    """Structured result for vendor scoring."""
    vendor_score: float
    risk_flags: list[str]
    recommendation: str


def score_financial_stability(data: dict) -> tuple[float, list[str]]:
    """Score financial stability (0-25 points)."""
    score = 0.0
    flags = []

    # Years in business (0-10 points)
    years = data.get('years_in_business', 0)
    if years >= 10:
        score += 10
    elif years >= 5:
        score += 7
    elif years >= 2:
        score += 4
    else:
        flags.append(f"Company young ({years} years), higher risk")
        score += 0

    # Funding/revenue (0-10 points)
    funding = data.get('funding_status', '')
    if funding in ['profitable', 'public']:
        score += 10
    elif funding == 'series_c_plus':
        score += 7
    elif funding in ['series_a', 'series_b']:
        score += 4
    else:
        flags.append(f"Funding unclear or early stage: {funding}")
        score += 0

    # M&A risk (0-5 points)
    ma_risk = data.get('ma_risk', 'unknown')
    if ma_risk == 'low':
        score += 5
    elif ma_risk == 'medium':
        score += 3
    else:
        flags.append(f"M&A risk: {ma_risk}")
        score += 0

    return score, flags


def score_product_maturity(data: dict) -> tuple[float, list[str]]:
    """Score product maturity (0-25 points)."""
    score = 0.0
    flags = []

    # Market position (0-10 points)
    position = data.get('market_position', '')
    if position == 'leader':
        score += 10
    elif position == 'challenger':
        score += 7
    elif position == 'niche':
        score += 4
    else:
        flags.append(f"Market position unclear: {position}")
        score += 0

    # Customer count (0-10 points)
    customers = data.get('customer_count', 0)
    if customers >= 1000:
        score += 10
    elif customers >= 100:
        score += 7
    elif customers >= 10:
        score += 4
    else:
        flags.append(f"Few customers ({customers}), limited validation")
        score += 0

    # Product roadmap (0-5 points)
    roadmap = data.get('public_roadmap', False)
    if roadmap:
        score += 5
    else:
        flags.append("No public roadmap, hard to assess future direction")
        score += 0

    return score, flags


def score_pricing_model(data: dict) -> tuple[float, list[str]]:
    """Score pricing model (0-25 points)."""
    score = 0.0
    flags = []

    # Pricing transparency (0-10 points)
    transparency = data.get('pricing_transparency', '')
    if transparency == 'public':
        score += 10
    elif transparency == 'quote_required':
        score += 5
    else:
        flags.append(f"Pricing opaque: {transparency}")
        score += 0

    # Predictability (0-10 points)
    model = data.get('pricing_model', '')
    if model in ['flat_rate', 'per_seat']:
        score += 10
    elif model == 'usage_based':
        score += 7
    else:
        flags.append(f"Pricing model unpredictable: {model}")
        score += 3

    # Lock-in cost (0-5 points)
    lock_in = data.get('lock_in_cost', 'unknown')
    if lock_in == 'low':
        score += 5
    elif lock_in == 'medium':
        score += 3
    else:
        flags.append(f"High lock-in cost or unknown: {lock_in}")
        score += 0

    return score, flags


def score_feature_fit(data: dict) -> tuple[float, list[str]]:
    """Score feature fit (0-25 points)."""
    score = 0.0
    flags = []

    # Core features (0-15 points)
    core_coverage = data.get('core_feature_coverage_percent', 0)
    if core_coverage >= 90:
        score += 15
    elif core_coverage >= 75:
        score += 10
    elif core_coverage >= 50:
        score += 5
    else:
        flags.append(f"Low core feature coverage: {core_coverage}%")
        score += 0

    # Customization (0-10 points)
    customization = data.get('customization_options', '')
    if customization in ['api', 'sdk']:
        score += 10
    elif customization == 'config_only':
        score += 5
    else:
        flags.append(f"Limited customization: {customization}")
        score += 0

    return score, flags


def calculate_vendor_score(data: dict) -> VendorScore:
    """Calculate overall vendor score."""
    total_score = 0.0
    all_flags = []

    stability_score, stability_flags = score_financial_stability(data)
    total_score += stability_score
    all_flags.extend(stability_flags)

    maturity_score, maturity_flags = score_product_maturity(data)
    total_score += maturity_score
    all_flags.extend(maturity_flags)

    pricing_score, pricing_flags = score_pricing_model(data)
    total_score += pricing_score
    all_flags.extend(pricing_flags)

    feature_score, feature_flags = score_feature_fit(data)
    total_score += feature_score
    all_flags.extend(feature_flags)

    # Determine recommendation
    if total_score > 70:
        recommendation = "PASS - Vendor meets quality standards"
    elif total_score >= 50:
        recommendation = "YELLOW FLAG - Proceed with caution, mitigate risks"
    else:
        recommendation = "RED FLAG - High risk, consider alternatives"

    return VendorScore(
        vendor_score=total_score,
        risk_flags=all_flags,
        recommendation=recommendation
    )


def main():
    parser = argparse.ArgumentParser(
        description="Score vendor quality and risk profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example vendor data file format (JSON):
{
  "years_in_business": 8,
  "funding_status": "series_c_plus",
  "ma_risk": "low",
  "market_position": "challenger",
  "customer_count": 500,
  "public_roadmap": true,
  "pricing_transparency": "public",
  "pricing_model": "per_seat",
  "lock_in_cost": "low",
  "core_feature_coverage_percent": 85,
  "customization_options": "api"
}
        """
    )

    parser.add_argument('--vendor-data', type=str, required=True,
                       help='JSON file with vendor information')

    args = parser.parse_args()

    # Load vendor data
    try:
        with open(args.vendor_data) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Vendor data file not found: {args.vendor_data}", file=sys.stderr)
        sys.exit(11)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in vendor data file: {e}", file=sys.stderr)
        sys.exit(11)

    # Calculate score
    result = calculate_vendor_score(data)

    # Output results
    print("Vendor Scorecard")
    print(f"{'='*60}")
    print(f"Overall Score: {result.vendor_score:.1f}/100")
    print("")
    print(f"Risk Flags ({len(result.risk_flags)}):")
    if result.risk_flags:
        for flag in result.risk_flags:
            print(f"  - {flag}")
    else:
        print("  (none)")
    print("")
    print(f"Recommendation: {result.recommendation}")

    # Determine exit code
    if result.vendor_score > 70:
        sys.exit(0)
    elif result.vendor_score >= 50:
        sys.exit(10)
    else:
        sys.exit(11)


if __name__ == '__main__':
    main()
