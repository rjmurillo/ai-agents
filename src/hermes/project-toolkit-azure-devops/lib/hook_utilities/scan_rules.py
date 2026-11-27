"""Rule-selection parsing shared by the two repository scanners."""

import sys


def parse_scan_rules(
    rules_str: str, available: tuple[str, ...], error_code: int
) -> tuple[str, ...]:
    if not rules_str:
        return available
    rules = tuple(rule.strip() for rule in rules_str.split(","))
    invalid = [rule for rule in rules if rule not in available]
    if invalid:
        print(f"error: unknown rules: {', '.join(invalid)}", file=sys.stderr)
        print(f"valid rules: {', '.join(available)}", file=sys.stderr)
        sys.exit(error_code)
    return rules
