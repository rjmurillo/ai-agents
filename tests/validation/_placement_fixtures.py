"""Shared Markdown content fixtures for the check_memory_placement tests.

Each constant is one memory body shaped to fire, or deliberately not fire, a
specific placement signal. Imported by ``test_check_memory_placement.py``
(pure classify tests) and ``test_check_memory_placement_cli.py`` (CLI tests).
"""

from __future__ import annotations

NORMATIVE_HEADING = """# Some Memory

## Constraints

1. First
2. Second
"""

EVIDENCE_INCIDENT = """# Incident Record

We noted that we must document this. We also must remember the impact.
This will never again happen the same way, we hope.
"""

SUSPECT_TERM_DENSITY = """# Suspect Memory

This must not be repeated. This should always be reviewed. This is
required for context.
"""

SUSPECT_ORDERED_ONLY = """# Suspect Ordered

1. Step one
2. Step two
3. Step three
4. Step four
5. Step five
"""

NORMATIVE_TERM_AND_ORDER = """# Combo

This MUST happen. This MUST NOT be skipped. This SHALL be documented.
This is required. This must not be forgotten.

1. One
2. Two
3. Three
4. Four
5. Five
"""

VALID_SUPPRESSION = (
    NORMATIVE_HEADING + "\n<!-- placement: evidence; reason: kept as rationale for ADR-0000 -->\n"
)

INVALID_SUPPRESSION = NORMATIVE_HEADING + "\n<!-- placement: evidence; reason: -->\n"

ROLE_CONTRACT = """# Some Agent

## Role

Does the thing.

## Authority

Decides the thing.
"""
