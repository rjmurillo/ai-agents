#!/usr/bin/env python3
"""Generate a prioritized mitigation roadmap from a threat model.

Parses a threat model markdown file and extracts threats to create
a prioritized mitigation roadmap.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Threat:
    """Represents a threat extracted from the threat model."""

    id: str
    element: str
    stride: str
    description: str
    likelihood: str
    impact: str
    risk: str
    status: str = "Planned"
    mitigations: list = field(default_factory=list)


RISK_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

ROADMAP_TEMPLATE = '''# Mitigation Roadmap: {scope}

**Generated**: {date}
**Source**: {source}

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Total Threats | {total_threats} |
| Critical | {critical_count} |
| High | {high_count} |
| Medium | {medium_count} |
| Low | {low_count} |

---

## Priority 1: Critical Risks

> Must address before production deployment

{critical_section}

---

## Priority 2: High Risks

> Address in next sprint/release

{high_section}

---

## Priority 3: Medium Risks

> Schedule for upcoming releases

{medium_section}

---

## Priority 4: Low Risks

> Address opportunistically or accept

{low_section}

---

## Implementation Timeline

| Phase | Focus | Threats | Target |
|-------|-------|---------|--------|
| Immediate | Critical risks | {critical_ids} | This sprint |
| Short-term | High risks | {high_ids} | Next 2 sprints |
| Medium-term | Medium risks | {medium_ids} | Next quarter |
| Long-term | Low risks | {low_ids} | As resources allow |

---

## Next Steps

1. [ ] Review roadmap with security team
2. [ ] Assign owners to Critical/High mitigations
3. [ ] Create tickets for immediate phase
4. [ ] Schedule follow-up review

---

## Appendix: All Threats by Risk

{threat_table}
'''


def parse_threat_matrix(content: str) -> list[Threat]:
    """Parse threats from markdown table.

    Args:
        content: Markdown content of threat model

    Returns:
        List of Threat objects
    """
    threats = []

    # Find threat matrix table
    table_pattern = r'\| ID \| Element \| STRIDE \| Threat \|.*?\n((?:\|.*\n)*)'
    match = re.search(table_pattern, content, re.IGNORECASE)

    if not match:
        return threats

    table_rows = match.group(1).strip().split('\n')

    for row in table_rows:
        # Skip separator rows
        if '---' in row:
            continue

        # Parse table row
        cells = [c.strip() for c in row.split('|')[1:-1]]
        if len(cells) >= 7:
            threat = Threat(
                id=cells[0],
                element=cells[1],
                stride=cells[2],
                description=cells[3],
                likelihood=cells[4],
                impact=cells[5],
                risk=cells[6],
                status=cells[7] if len(cells) > 7 else "Planned",
            )
            threats.append(threat)

    return threats


def categorize_by_risk(threats: list[Threat]) -> dict[str, list[Threat]]:
    """Group threats by risk level.

    Args:
        threats: List of Threat objects

    Returns:
        Dictionary mapping risk level to threats
    """
    categories = {"Critical": [], "High": [], "Medium": [], "Low": []}

    for threat in threats:
        risk = threat.risk
        # Normalize risk level
        for level in categories:
            if level.lower() in risk.lower():
                categories[level].append(threat)
                break
        else:
            categories["Medium"].append(threat)

    return categories


def format_threat_section(threats: list[Threat]) -> str:
    """Format threats for a roadmap section.

    Args:
        threats: List of threats for this section

    Returns:
        Formatted markdown
    """
    if not threats:
        return "_No threats at this level_"

    lines = []
    for t in threats:
        lines.append(f"### {t.id}: {t.description}")
        lines.append("")
        lines.append(f"- **Element**: {t.element}")
        lines.append(f"- **STRIDE**: {t.stride}")
        lines.append(f"- **Likelihood**: {t.likelihood}")
        lines.append(f"- **Impact**: {t.impact}")
        lines.append(f"- **Status**: {t.status}")
        lines.append("")
        lines.append("**Recommended Mitigations**:")
        lines.append("")
        lines.append("- [ ] [Add specific mitigation]")
        lines.append("- [ ] [Add specific mitigation]")
        lines.append("")

    return "\n".join(lines)


def format_threat_table(threats: list[Threat]) -> str:
    """Format all threats as a summary table.

    Args:
        threats: All threats

    Returns:
        Markdown table
    """
    lines = [
        "| ID | STRIDE | Risk | Description | Status |",
        "|----|--------|------|-------------|--------|",
    ]

    # Sort by risk
    sorted_threats = sorted(threats, key=lambda t: RISK_ORDER.get(t.risk, 99))

    for t in sorted_threats:
        lines.append(f"| {t.id} | {t.stride} | {t.risk} | {t.description} | {t.status} |")

    return "\n".join(lines)


def extract_scope(content: str) -> str:
    """Extract scope from threat model header.

    Args:
        content: Markdown content

    Returns:
        Scope string or default
    """
    match = re.search(r'# Threat Model: (.+)', content)
    if match:
        return match.group(1).strip()

    match = re.search(r'## Scope.*?Subject\*\*: (.+)', content, re.DOTALL)
    if match:
        return match.group(1).strip()

    return "Unknown Scope"


def generate_roadmap(input_path: Path, output_path: Path) -> int:
    """Generate mitigation roadmap from threat model.

    Args:
        input_path: Path to threat model markdown
        output_path: Path to write roadmap

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    content = input_path.read_text()
    threats = parse_threat_matrix(content)

    if not threats:
        print("Warning: No threats found in threat matrix", file=sys.stderr)
        print("Ensure the threat model has a table with header:")
        print("| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |")

    categorized = categorize_by_risk(threats)
    scope = extract_scope(content)

    roadmap = ROADMAP_TEMPLATE.format(
        scope=scope,
        date=datetime.now().strftime("%Y-%m-%d"),
        source=input_path.name,
        total_threats=len(threats),
        critical_count=len(categorized["Critical"]),
        high_count=len(categorized["High"]),
        medium_count=len(categorized["Medium"]),
        low_count=len(categorized["Low"]),
        critical_section=format_threat_section(categorized["Critical"]),
        high_section=format_threat_section(categorized["High"]),
        medium_section=format_threat_section(categorized["Medium"]),
        low_section=format_threat_section(categorized["Low"]),
        critical_ids=", ".join(t.id for t in categorized["Critical"]) or "None",
        high_ids=", ".join(t.id for t in categorized["High"]) or "None",
        medium_ids=", ".join(t.id for t in categorized["Medium"]) or "None",
        low_ids=", ".join(t.id for t in categorized["Low"]) or "None",
        threat_table=format_threat_table(threats),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(roadmap)

    print(f"Generated mitigation roadmap: {output_path}")
    print(f"Threats processed: {len(threats)}")
    print(f"  Critical: {len(categorized['Critical'])}")
    print(f"  High: {len(categorized['High'])}")
    print(f"  Medium: {len(categorized['Medium'])}")
    print(f"  Low: {len(categorized['Low'])}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a prioritized mitigation roadmap from a threat model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_mitigation_roadmap.py --input auth-threats.md --output auth-roadmap.md
  python generate_mitigation_roadmap.py -i threats.md -o roadmap.md
        """,
    )

    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Path to the threat model markdown file",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Output path for the mitigation roadmap",
    )

    args = parser.parse_args()

    try:
        return generate_roadmap(args.input, args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
