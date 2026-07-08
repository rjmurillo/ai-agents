#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate a structured threat matrix document.

Creates a markdown threat model template with STRIDE categories
and risk rating structure.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _PLUGIN_ROOT:
    _LIB_DIR = Path(_PLUGIN_ROOT) / "lib"
else:
    _LIB_DIR = Path(__file__).resolve().parents[3] / "lib"

if not os.path.isdir(_LIB_DIR):
    raise RuntimeError(
        "Expected portability helper lib directory not found: "
        f"{_LIB_DIR}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
        "plugin root, or run from an ai-agents checkout."
    )
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_utilities.path_safety import validate_path_no_traversal  # noqa: E402

STRIDE_CATEGORIES = [
    ("S", "Spoofing", "Pretending to be something or someone else"),
    ("T", "Tampering", "Modifying data or code without authorization"),
    ("R", "Repudiation", "Denying having performed an action"),
    ("I", "Information Disclosure", "Exposing information to unauthorized parties"),
    ("D", "Denial of Service", "Making a system unavailable or degraded"),
    ("E", "Elevation of Privilege", "Gaining capabilities without authorization"),
]

TEMPLATE = '''# Threat Model: {scope}

**Created**: {date}
**Version**: 1.0
**Status**: Draft

## Scope

- **Subject**: {scope}
- **Boundaries**: [Define what is IN and OUT of scope]
- **Stakeholders**: [Who requested, who will review]

---

## Architecture Overview

```text
[Add Data Flow Diagram here]

+----------+     HTTPS      +----------+     SQL       +----------+
| External | -------------> |  Process | ------------> |  Data    |
|  Entity  |                |          |               |  Store   |
+----------+                +----------+               +----------+
     |                           |
     |     Trust Boundary        |
     +---------------------------+
```

### Components

| ID | Name | Type | Description |
|----|------|------|-------------|
| C001 | [Component] | Process/Store/Entity | [Description] |

### Trust Boundaries

| ID | Name | Description |
|----|------|-------------|
| TB001 | [Boundary] | [What privilege change occurs] |

### Data Flows

| ID | Source | Destination | Data | Protocol |
|----|--------|-------------|------|----------|
| DF001 | [From] | [To] | [What data] | [HTTP/SQL/etc] |

---

## STRIDE Analysis

{stride_sections}

---

## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk | Mitigation Status |
|----|---------|--------|--------|------------|--------|------|-------------------|
| T001 | [Element] | [S/T/R/I/D/E] | [Threat description] | [H/M/L] | [H/M/L] | [Crit/High/Med/Low] | [Planned/In Progress/Done] |

---

## Risk Summary

### By Risk Level

| Risk Level | Count | Threats |
|------------|-------|---------|
| Critical | 0 | |
| High | 0 | |
| Medium | 0 | |
| Low | 0 | |

### By STRIDE Category

| Category | Count | Notes |
|----------|-------|-------|
| Spoofing | 0 | |
| Tampering | 0 | |
| Repudiation | 0 | |
| Information Disclosure | 0 | |
| Denial of Service | 0 | |
| Elevation of Privilege | 0 | |

---

## Mitigations

### Critical/High Priority

[List mitigations for Critical and High risk threats]

### Medium Priority

[List mitigations for Medium risk threats]

### Accepted Risks

[List threats accepted with justification]

---

## Validation Checklist

- [ ] All components have at least one threat identified
- [ ] All trust boundaries documented
- [ ] All STRIDE categories considered
- [ ] All Critical/High risks have mitigations planned
- [ ] Peer review completed
- [ ] Stakeholder sign-off obtained

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | {date} | [Author] | Initial threat model |

---

## References

- OWASP Threat Modeling: https://owasp.org/www-community/Threat_Modeling
- Microsoft STRIDE: https://docs.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
'''


def generate_stride_sections() -> str:
    """Generate STRIDE category sections."""
    sections = []
    for code, name, description in STRIDE_CATEGORIES:
        section = f'''### {code} - {name}

**Definition**: {description}

**Questions to Ask**:
- [Category-specific questions]

**Identified Threats**:

| ID | Element | Threat | Risk |
|----|---------|--------|------|
| | | | |
'''
        sections.append(section)
    return "\n".join(sections)


def generate_threat_matrix(scope: str, output_path: Path) -> int:
    """Generate threat matrix document.

    Args:
        scope: Name/description of what is being threat modeled
        output_path: Path to write the output file

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    date = datetime.now().strftime("%Y-%m-%d")
    stride_sections = generate_stride_sections()

    content = TEMPLATE.format(
        scope=scope,
        date=date,
        stride_sections=stride_sections,
    )

    # Validate path to prevent traversal (CWE-22)
    validate_path_no_traversal(output_path, "output path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    print(f"Generated threat matrix: {output_path}")
    print(f"Scope: {scope}")
    print(f"STRIDE categories: {len(STRIDE_CATEGORIES)}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a structured threat matrix document",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_threat_matrix.py --scope "Auth Service" --output auth-threats.md
  python generate_threat_matrix.py --scope "Payment API" --output ./threat-models/payment.md
        """,
    )

    parser.add_argument(
        "--scope",
        required=True,
        help="Name or description of what is being threat modeled",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the threat matrix document",
    )

    args = parser.parse_args()

    try:
        return generate_threat_matrix(args.scope, args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
