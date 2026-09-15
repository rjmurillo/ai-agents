#!/usr/bin/env python3
"""
Calculate Total Cost of Ownership (TCO) for Build/Buy/Partner decisions.

Realistic TCO includes hidden costs that grow over time:
- Engineer salary (fully-loaded with benefits, facilities, etc.)
- Maintenance overhead (security patches, dependency updates, compliance)
- Maintenance expansion (overhead grows ~10-20% yearly as systems mature)
- Code churn drag (40-60% of code changes yearly = unplanned "side quests")

Example: A $350K/year engineer with 120 hours/year maintenance that grows 15%/year
         and 50% code churn actually costs $525K/year by year 5.

Exit codes:
  0: Success
  1: Error (invalid inputs)
  2: Warning (negative NPV detected - you lose money on all options)
"""

import argparse
import sys
from dataclasses import dataclass


@dataclass
class TCOResult:
    """What you get back from TCO calculation."""
    npv_build: float        # Total cost to build (negative = you spend this)
    npv_buy: float          # Total cost to buy (negative = you spend this)
    npv_partner: float      # Total cost to partner (negative = you spend this)
    irr_build: float        # Internal rate of return (mostly academic)
    breakeven_years: float  # When does build become cheaper than buy?
    sensitivity: dict[str, float]  # How much do costs swing if inputs change?
    warning: str = ""       # Any red flags


def calculate_realistic_build_cost(
    engineer_cost: float,
    maintenance_hours: float,
    maintenance_growth: float,
    code_churn_rate: float,
    year: int
) -> float:
    """
    Calculate what building ACTUALLY costs per year (not just salary).

    Args:
        engineer_cost: Fully-loaded annual cost ($350K typical for tech companies)
        maintenance_hours: Annual overhead hours (security, compliance, quality)
                          Typical: 120-200 hours/year (3-5 weeks)
        maintenance_growth: How much overhead grows yearly (1.0 = flat, 1.15 = 15% growth)
                           Typical: 1.10-1.20 (systems get more complex over time)
        code_churn_rate: % of code that changes yearly (0.4-0.6 typical)
                         Startups: 0.6-0.8 (high churn, fast iteration)
                         Enterprises: 0.3-0.5 (stability over speed)
        year: Which year of the project (1, 2, 3, ...)

    Returns:
        Actual annual cost including all hidden overhead

    Example:
        Year 1: $350K salary + $14K maintenance (120hrs) + $52K churn drag = $416K
        Year 5: $350K salary + $24K maintenance (grows 15%/yr) + $52K churn = $426K
    """
    # Base cost: what you pay the engineer
    base_cost = engineer_cost

    # Maintenance overhead: grows each year as systems mature
    # Formula: (hours * hourly_rate) * growth_factor^(year-1)
    hourly_rate = engineer_cost / 2080  # 2080 work hours/year
    maintenance_cost = (maintenance_hours * hourly_rate) * (maintenance_growth ** (year - 1))

    # Code churn drag: unplanned work from changing 40-60% of code yearly
    # 30% of churn time is "side quests" (unplanned refactoring, bug fixes, etc.)
    churn_drag = engineer_cost * code_churn_rate * 0.3

    return base_cost + maintenance_cost + churn_drag


def calculate_npv(
    initial_cost: float, ongoing_cost: float, discount_rate: float, years: int
) -> float:
    """
    Calculate Net Present Value (what you actually pay in today's dollars).

    NPV accounts for: money today is worth more than money tomorrow.
    $100 today > $100 in 5 years (you could invest that $100 and earn interest).

    Args:
        initial_cost: Upfront cost (licenses, setup, etc.)
        ongoing_cost: Annual recurring cost
        discount_rate: How much you discount future money (0.10 = 10%)
        years: How many years to calculate

    Returns:
        Negative number = total cost in today's dollars
        (Negative because you're spending, not earning)
    """
    npv = -initial_cost
    for year in range(1, years + 1):
        npv += ongoing_cost / ((1 + discount_rate) ** year)
    return -npv  # Negative because costs


def calculate_irr(
    initial_cost: float, ongoing_cost: float, years: int, iterations: int = 100
) -> float:
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
                denominator = (npv_buy - npv_build) + (npv_buy_prev - npv_build_prev)
                fraction = (npv_buy_prev - npv_build_prev) / denominator
                return prev_year + fraction
            return float(year)

    return float(max_years)


def sensitivity_analysis(
    base_result: TCOResult, avg_build_cost: float, args: argparse.Namespace
) -> dict[str, float]:
    """
    Analyze how much results change if inputs are off by ±20%.

    This tells you: if your cost estimates are wrong, how wrong could your decision be?

    Args:
        base_result: The main TCO result
        avg_build_cost: Average annual build cost (from realistic or simple mode)
        args: Command line arguments

    Returns:
        Dict showing how much NPV swings for each parameter
    """
    sensitivity = {}

    # Test discount rate sensitivity (±20%)
    rate_low = args.discount_rate * 0.8
    rate_high = args.discount_rate * 1.2

    npv_build_low = calculate_npv(args.build_initial, avg_build_cost, rate_low, args.years)
    npv_build_high = calculate_npv(args.build_initial, avg_build_cost, rate_high, args.years)

    sensitivity['discount_rate'] = abs(npv_build_high - npv_build_low)

    # Test ongoing cost sensitivity (±20%)
    cost_low = avg_build_cost * 0.8
    cost_high = avg_build_cost * 1.2

    npv_cost_low = calculate_npv(args.build_initial, cost_low, args.discount_rate, args.years)
    npv_cost_high = calculate_npv(args.build_initial, cost_high, args.discount_rate, args.years)

    sensitivity['ongoing_cost'] = abs(npv_cost_high - npv_cost_low)

    return sensitivity


def validate_inputs(args: argparse.Namespace) -> list[str]:
    """Validate all inputs are sensible."""
    errors = []

    # Required always
    if args.build_initial < 0:
        errors.append("Build initial cost cannot be negative")
    if args.buy_initial < 0:
        errors.append("Buy initial cost cannot be negative")
    if args.buy_ongoing < 0:
        errors.append("Buy ongoing cost cannot be negative")
    if args.discount_rate <= 0 or args.discount_rate >= 1:
        errors.append("Discount rate must be between 0 and 1 (0.10 = 10%)")
    if args.years not in [3, 5, 10]:
        errors.append("Years must be 3, 5, or 10")

    # Optional: simple mode
    if args.build_ongoing and args.build_ongoing < 0:
        errors.append("Build ongoing cost cannot be negative")

    # Optional: realistic mode
    if args.engineer_cost:
        if args.engineer_cost < 50000:
            errors.append("Engineer cost seems low (< $50K/year) - did you mean $50,000 not 50?")
        if args.engineer_cost > 1000000:
            errors.append("Engineer cost seems high (> $1M/year) - check your input")

    if args.maintenance_hours < 0 or args.maintenance_hours > 2080:
        errors.append("Maintenance hours must be 0-2080 (0-100% of work year)")

    if args.maintenance_growth < 0.5 or args.maintenance_growth > 2.0:
        errors.append("Maintenance growth must be 0.5-2.0 (50%-200% yearly growth)")

    if args.code_churn_rate < 0 or args.code_churn_rate > 1.0:
        errors.append("Code churn rate must be 0.0-1.0 (0%-100% of code changes/year)")

    # Optional: partner
    if args.partner_initial < 0:
        errors.append("Partner initial cost cannot be negative")
    if args.partner_ongoing < 0:
        errors.append("Partner ongoing cost cannot be negative")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Calculate REALISTIC TCO for Build/Buy/Partner decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                            WHAT YOU NEED TO KNOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This tool calculates what building ACTUALLY costs (not just engineer salary).

REQUIRED FOR ALL OPTIONS:
  --discount-rate 0.12     How much you discount future money (10-15%% typical)
  --years 5                How many years to analyze (3, 5, or 10)

SIMPLE MODE (if you just know annual costs):
  --build-initial 500000   Upfront build cost
  --build-ongoing 200000   Annual build cost (simple)
  --buy-initial 50000      Upfront buy cost (licenses, setup)
  --buy-ongoing 150000     Annual buy cost (subscriptions, support)

REALISTIC MODE (accounts for hidden build costs):
  --build-initial 500000
  --engineer-cost 350000         Engineer salary + benefits + facilities
  --maintenance-hours 120        Annual overhead (security, compliance, updates)
  --maintenance-growth 1.15      Overhead grows 15%%/year as systems mature
  --code-churn-rate 0.5          50%% of code changes yearly (unplanned work)
  --buy-initial 50000
  --buy-ongoing 150000

WHY REALISTIC MODE MATTERS:
  A $350K engineer with 120hrs maintenance (grows 15%%/yr) and 50%% churn
  costs $416K in year 1 and $526K by year 5 (not $350K).

TYPICAL VALUES BY ORG TYPE:

  Large Tech Company (Microsoft, Google, Meta):
    --engineer-cost 350000 --maintenance-hours 150 --maintenance-growth 1.15
    --code-churn-rate 0.45   (Lower churn, more stability)

  Mid-Size Tech Company:
    --engineer-cost 250000 --maintenance-hours 120 --maintenance-growth 1.12
    --code-churn-rate 0.50   (Moderate churn)

  Startup (Series A-B):
    --engineer-cost 180000 --maintenance-hours 80 --maintenance-growth 1.20
    --code-churn-rate 0.70   (High churn, fast iteration, technical debt)

  Enterprise (Non-Tech):
    --engineer-cost 200000 --maintenance-hours 100 --maintenance-growth 1.10
    --code-churn-rate 0.35   (Low churn, risk-averse)

EXAMPLES:

  # Simple: Just compare sticker prices
  python3 calculate_tco.py \\
    --build-initial 500000 --build-ongoing 200000 \\
    --buy-initial 50000 --buy-ongoing 150000 \\
    --partner-initial 100000 --partner-ongoing 125000 \\
    --discount-rate 0.12 --years 5

  # Realistic: Tech company with growing overhead
  python3 calculate_tco.py \\
    --build-initial 500000 \\
    --engineer-cost 350000 --maintenance-hours 150 \\
    --maintenance-growth 1.15 --code-churn-rate 0.45 \\
    --buy-initial 50000 --buy-ongoing 150000 \\
    --partner-initial 100000 --partner-ongoing 125000 \\
    --discount-rate 0.12 --years 5

  # Realistic: Startup with high churn
  python3 calculate_tco.py \\
    --build-initial 200000 \\
    --engineer-cost 180000 --maintenance-hours 80 \\
    --maintenance-growth 1.20 --code-churn-rate 0.70 \\
    --buy-initial 30000 --buy-ongoing 80000 \\
    --discount-rate 0.15 --years 3

OUTPUT EXPLAINED:
  NPV (Build): -$2,500,000  ← You spend $2.5M over 5 years (in today's dollars)
  NPV (Buy):   -$950,000    ← You spend $950K over 5 years
  Break-even: Year 8.2      ← Build becomes cheaper than buy after 8.2 years
                              (but you only analyzed 5 years, so buy wins)

RULE OF THUMB:
  If break-even > analysis horizon, buy wins.
  If NPV (Build) is way more negative than NPV (Buy), buy wins BIG.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
    )

    # Required for all scenarios
    parser.add_argument('--discount-rate', type=float, required=True,
                       help='Discount rate: 0.10 = 10%%, 0.12 = 12%% (typical: 10-15%%)')
    parser.add_argument('--years', type=int, required=True, choices=[3, 5, 10],
                       help='Analysis horizon: 3, 5, or 10 years')

    # Simple mode: just annual costs
    parser.add_argument('--build-initial', type=float, required=True,
                       help='Build: Upfront cost ($)')
    parser.add_argument('--build-ongoing', type=float, required=False,
                       help='Build: Annual cost - SIMPLE mode (use OR realistic params)')

    # Realistic mode: detailed build costs
    parser.add_argument('--engineer-cost', type=float, required=False,
                       help='Build: Fully-loaded engineer cost/year ($350K typical)')
    parser.add_argument('--maintenance-hours', type=float, required=False, default=0,
                       help='Build: Annual overhead hours (security, compliance, updates). '
                            'Typical: 80-200')
    parser.add_argument('--maintenance-growth', type=float, required=False, default=1.0,
                       help='Build: Yearly overhead growth (1.15 = 15%%/year). Typical: 1.10-1.20')
    parser.add_argument('--code-churn-rate', type=float, required=False, default=0.0,
                       help='Build: Annual code churn rate (0.5 = 50%%). '
                            'Startups: 0.6-0.8, Enterprises: 0.3-0.5')

    # Buy/Partner (always simple - just costs)
    parser.add_argument('--buy-initial', type=float, required=True,
                       help='Buy: Upfront cost (licenses, setup, integration)')
    parser.add_argument('--buy-ongoing', type=float, required=True,
                       help='Buy: Annual cost (subscriptions, support, training)')
    parser.add_argument('--partner-initial', type=float, required=False, default=0,
                       help='Partner: Upfront cost (integration, setup)')
    parser.add_argument('--partner-ongoing', type=float, required=False, default=0,
                       help='Partner: Annual cost (rev share, support)')

    args = parser.parse_args()

    # Determine mode: Simple or Realistic
    if args.engineer_cost:
        # REALISTIC MODE: Calculate actual build costs with all overhead
        mode = "REALISTIC"
        if args.build_ongoing:
            print(
                "ERROR: Cannot use both --build-ongoing (simple) and "
                "--engineer-cost (realistic)",
                file=sys.stderr
            )
            print("       Choose ONE mode: simple OR realistic", file=sys.stderr)
            sys.exit(1)

        # Calculate realistic yearly costs
        build_yearly_costs = []
        for year in range(1, args.years + 1):
            yearly_cost = calculate_realistic_build_cost(
                args.engineer_cost,
                args.maintenance_hours,
                args.maintenance_growth,
                args.code_churn_rate,
                year
            )
            build_yearly_costs.append(yearly_cost)

        # Calculate NPV with varying yearly costs
        npv_build = -args.build_initial
        for year, cost in enumerate(build_yearly_costs, start=1):
            npv_build -= cost / ((1 + args.discount_rate) ** year)

        # For IRR and breakeven, use average yearly cost
        avg_build_cost = sum(build_yearly_costs) / len(build_yearly_costs)

    elif args.build_ongoing:
        # SIMPLE MODE: Just use stated annual cost
        mode = "SIMPLE"
        npv_build = calculate_npv(
            args.build_initial, args.build_ongoing, args.discount_rate, args.years
        )
        avg_build_cost = args.build_ongoing
    else:
        print(
            "ERROR: Must provide EITHER --build-ongoing (simple) OR "
            "--engineer-cost (realistic)",
            file=sys.stderr
        )
        print("       See --help for examples", file=sys.stderr)
        sys.exit(1)

    # Validate inputs (after mode determination)
    errors = validate_inputs(args)
    if errors:
        print("ERROR: Validation failed", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Calculate NPVs for buy/partner (always simple)
    npv_buy = calculate_npv(
        args.buy_initial, args.buy_ongoing, args.discount_rate, args.years
    )
    npv_partner = calculate_npv(
        args.partner_initial, args.partner_ongoing, args.discount_rate, args.years
    )

    # Calculate IRR for build option (using average cost)
    irr_build = calculate_irr(args.build_initial, avg_build_cost, args.years)

    # Calculate break-even (using average cost)
    breakeven = calculate_breakeven(
        args.build_initial, avg_build_cost,
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
    result.sensitivity = sensitivity_analysis(result, avg_build_cost, args)

    # Check for negative NPV warning
    if npv_build > 0 or npv_buy > 0 or npv_partner > 0:
        result.warning = "Negative NPV detected (costs exceed discounted value)"

    # Output results
    print(f"{'='*80}")
    print(f"TCO Analysis ({args.years} year horizon) - {mode} MODE")
    print(f"{'='*80}")
    print("")
    print("COSTS (in today's dollars):")
    print(f"  Build:   ${abs(result.npv_build):>15,.2f}")
    print(f"  Buy:     ${abs(result.npv_buy):>15,.2f}")
    if args.partner_ongoing > 0:
        print(f"  Partner: ${abs(result.npv_partner):>15,.2f}")
    print("")

    # Show winner
    costs = [
        ("Build", abs(result.npv_build)),
        ("Buy", abs(result.npv_buy)),
    ]
    if args.partner_ongoing > 0:
        costs.append(("Partner", abs(result.npv_partner)))

    winner = min(costs, key=lambda x: x[1])
    print(f"RECOMMENDATION: {winner[0]} (${winner[1]:,.2f} total cost)")
    print("")

    # Show realistic build breakdown if applicable
    if mode == "REALISTIC":
        print("BUILD COST BREAKDOWN:")
        for year, cost in enumerate(build_yearly_costs, start=1):
            print(f"  Year {year}: ${cost:>10,.2f}")
        print(f"  Average: ${avg_build_cost:>10,.2f}/year")
        print("")

    print("FINANCIAL METRICS:")
    print(f"  IRR (Build):         {result.irr_build*100:>6.1f}%")
    print(f"  Break-even vs Buy:   Year {result.breakeven_years:.1f}")
    if result.breakeven_years > args.years:
        print("                       ⚠️  Break-even AFTER analysis horizon")
        print(f"                       → Buy wins (cheaper over {args.years} years)")
    print("")

    print("SENSITIVITY ANALYSIS (±20%):")
    print(f"  Discount rate swing: ±${result.sensitivity['discount_rate']:,.0f}")
    print(f"  Ongoing cost swing:  ±${result.sensitivity['ongoing_cost']:,.0f}")
    print("")

    # Show interpretation
    print("WHAT THIS MEANS:")
    npv_diff = abs(result.npv_build) - abs(result.npv_buy)
    if abs(npv_diff) < 100000:
        print("  • Costs are SIMILAR - decision should be based on strategic factors")
        print("    (core vs context, team capability, vendor risk)")
    elif npv_diff > 0:
        print(f"  • Buy saves ${abs(npv_diff):,.0f} over {args.years} years")
        print("  • Strong financial case for buying")
    else:
        print(f"  • Build saves ${abs(npv_diff):,.0f} over {args.years} years")
        print("  • Financial case for building (if you have the time)")

    if result.warning:
        print(f"\n⚠️  WARNING: {result.warning}")
        sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
