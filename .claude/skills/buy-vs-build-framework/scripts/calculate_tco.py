#!/usr/bin/env python3
"""
Calculate Total Cost of Ownership (TCO) for Build/Buy/Partner decisions.

Outputs NPV, IRR, break-even timeline, and sensitivity analysis.
Exit codes:
  0: Success
  1: Error (missing required cost categories)
  2: Warning (negative NPV detected)
"""

import argparse
import sys
from dataclasses import dataclass


@dataclass
class TCOResult:
    """Structured result for TCO calculation."""
    npv_build: float
    npv_buy: float
    npv_partner: float
    irr_build: float
    breakeven_years: float
    sensitivity: dict[str, float]
    warning: str = ""


def calculate_npv(initial_cost: float, ongoing_cost: float, discount_rate: float, years: int) -> float:
    """Calculate Net Present Value."""
    npv = -initial_cost
    for year in range(1, years + 1):
        npv += ongoing_cost / ((1 + discount_rate) ** year)
    return -npv  # Negative because costs


def calculate_irr(initial_cost: float, ongoing_cost: float, years: int, iterations: int = 100) -> float:
    """Calculate Internal Rate of Return using binary search."""
    low, high = -0.99, 1.0

    for _ in range(iterations):
        mid = (low + high) / 2
        npv = calculate_npv(initial_cost, ongoing_cost, mid, years)

        if abs(npv) < 0.01:
            return mid
        elif npv > 0:
            low = mid
        else:
            high = mid

    return mid


def calculate_breakeven(build_initial: float, build_ongoing: float,
                       buy_initial: float, buy_ongoing: float,
                       discount_rate: float, max_years: int = 20) -> float:
    """Calculate break-even point in years."""
    for year in range(1, max_years + 1):
        npv_build = calculate_npv(build_initial, build_ongoing, discount_rate, year)
        npv_buy = calculate_npv(buy_initial, buy_ongoing, discount_rate, year)

        if npv_build < npv_buy:
            # Interpolate for fractional year
            if year == 1:
                return 1.0
            prev_year = year - 1
            npv_build_prev = calculate_npv(build_initial, build_ongoing, discount_rate, prev_year)
            npv_buy_prev = calculate_npv(buy_initial, buy_ongoing, discount_rate, prev_year)

            if (npv_buy - npv_build) != 0:
                fraction = (npv_buy_prev - npv_build_prev) / ((npv_buy - npv_build) + (npv_buy_prev - npv_build_prev))
                return prev_year + fraction
            return float(year)

    return float(max_years)


def sensitivity_analysis(base_result: TCOResult, args: argparse.Namespace) -> dict[str, float]:
    """Analyze sensitivity to key parameters."""
    sensitivity = {}

    # Test discount rate sensitivity (±20%)
    rate_low = args.discount_rate * 0.8
    rate_high = args.discount_rate * 1.2

    npv_build_low = calculate_npv(args.build_initial, args.build_ongoing, rate_low, args.years)
    npv_build_high = calculate_npv(args.build_initial, args.build_ongoing, rate_high, args.years)

    sensitivity['discount_rate'] = abs(npv_build_high - npv_build_low)

    # Test ongoing cost sensitivity (±20%)
    cost_low = args.build_ongoing * 0.8
    cost_high = args.build_ongoing * 1.2

    npv_cost_low = calculate_npv(args.build_initial, cost_low, args.discount_rate, args.years)
    npv_cost_high = calculate_npv(args.build_initial, cost_high, args.discount_rate, args.years)

    sensitivity['ongoing_cost'] = abs(npv_cost_high - npv_cost_low)

    return sensitivity


def validate_inputs(args: argparse.Namespace) -> list[str]:
    """Validate required cost categories are present."""
    errors = []

    if args.build_initial < 0:
        errors.append("Build initial cost cannot be negative")
    if args.build_ongoing < 0:
        errors.append("Build ongoing cost cannot be negative")
    if args.buy_initial < 0:
        errors.append("Buy initial cost cannot be negative")
    if args.buy_ongoing < 0:
        errors.append("Buy ongoing cost cannot be negative")
    if args.partner_initial < 0:
        errors.append("Partner initial cost cannot be negative")
    if args.partner_ongoing < 0:
        errors.append("Partner ongoing cost cannot be negative")
    if args.discount_rate <= 0 or args.discount_rate >= 1:
        errors.append("Discount rate must be between 0 and 1")
    if args.years not in [3, 5, 10]:
        errors.append("Years must be 3, 5, or 10")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Calculate TCO for Build/Buy/Partner decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 calculate_tco.py --build-initial 500000 --build-ongoing 100000 \\
                           --buy-initial 50000 --buy-ongoing 200000 \\
                           --partner-initial 100000 --partner-ongoing 150000 \\
                           --discount-rate 0.12 --years 5
        """
    )

    parser.add_argument('--build-initial', type=float, required=True,
                       help='Initial build costs ($)')
    parser.add_argument('--build-ongoing', type=float, required=True,
                       help='Annual build costs ($)')
    parser.add_argument('--buy-initial', type=float, required=True,
                       help='Initial buy costs ($)')
    parser.add_argument('--buy-ongoing', type=float, required=True,
                       help='Annual buy costs ($)')
    parser.add_argument('--partner-initial', type=float, required=True,
                       help='Initial partner costs ($)')
    parser.add_argument('--partner-ongoing', type=float, required=True,
                       help='Annual partner costs ($)')
    parser.add_argument('--discount-rate', type=float, required=True,
                       help='Discount rate (0.10 = 10%%)')
    parser.add_argument('--years', type=int, required=True, choices=[3, 5, 10],
                       help='Analysis horizon (3, 5, or 10 years)')

    args = parser.parse_args()

    # Validate inputs
    errors = validate_inputs(args)
    if errors:
        print("ERROR: Validation failed", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Calculate NPVs
    npv_build = calculate_npv(args.build_initial, args.build_ongoing, args.discount_rate, args.years)
    npv_buy = calculate_npv(args.buy_initial, args.buy_ongoing, args.discount_rate, args.years)
    npv_partner = calculate_npv(args.partner_initial, args.partner_ongoing, args.discount_rate, args.years)

    # Calculate IRR for build option
    irr_build = calculate_irr(args.build_initial, args.build_ongoing, args.years)

    # Calculate break-even
    breakeven = calculate_breakeven(
        args.build_initial, args.build_ongoing,
        args.buy_initial, args.buy_ongoing,
        args.discount_rate
    )

    # Create result
    result = TCOResult(
        npv_build=npv_build,
        npv_buy=npv_buy,
        npv_partner=npv_partner,
        irr_build=irr_build,
        breakeven_years=breakeven,
        sensitivity={}
    )

    # Sensitivity analysis
    result.sensitivity = sensitivity_analysis(result, args)

    # Check for negative NPV warning
    if npv_build > 0 or npv_buy > 0 or npv_partner > 0:
        result.warning = "Negative NPV detected (costs exceed discounted value)"

    # Output results
    print(f"TCO Analysis ({args.years} year horizon)")
    print(f"{'='*60}")
    print(f"NPV (Build):    ${result.npv_build:,.2f}")
    print(f"NPV (Buy):      ${result.npv_buy:,.2f}")
    print(f"NPV (Partner):  ${result.npv_partner:,.2f}")
    print("")
    print(f"IRR (Build):    {result.irr_build*100:.1f}%")
    print(f"Break-even:     Year {result.breakeven_years:.1f}")
    print("")
    print("Sensitivity Analysis (±20%)")
    print(f"  Discount rate: ±${result.sensitivity['discount_rate']:,.0f}")
    print(f"  Ongoing cost:  ±${result.sensitivity['ongoing_cost']:,.0f}")

    if result.warning:
        print(f"\nWARNING: {result.warning}")
        sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
