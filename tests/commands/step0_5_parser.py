"""Parser-side implementation of REQ-008 Step 0.5 Memory-First Gate.

Refs #1951. Used by `tests/commands/test_spec_step0_5.py`. Implements the
ProvisionalTier computation defined in REQ-008 AC-02 as Python so the
gate can be exercised deterministically without an LLM session.

The parser reads spec.md to extract Step 0.5 sections by stable heading
anchors (not line offsets) so prose churn within a section does not
break the tests. It is NOT a replacement for the model-level enforcement:
the gate at runtime is enforced by the LLM following the spec.md
instructions. This parser exists so tests can pin behavior at CI time.

Public symbols:

- `compute_provisional_tier(q4_text, entity_count)`: returns int 1-5
- `extract_step0_5_block(spec_text)`: full Step 0.5 markdown block
- `extract_step0_5_subsection(spec_text, heading)`: one named subsection
- `extract_step9_block(spec_text)`: Step 9 full block (for 9d checks)
- `has_guard_string(spec_text)`: True if partial-M2 guard is present

The parser deliberately avoids regex-anchored line numbers; section
boundaries use the next sibling heading at the same depth.
"""

from __future__ import annotations

import re

STEP_0_5_HEADING = "### Step 0.5: Memory-First Gate (blocking, runs after Step 0)"
STEP_1_HEADING_RE = r"^---\s*$"
GUARD_STRING = "<!-- step0.5:incomplete-without-2b -->"

PROVISIONAL_TIER_HOURS_DEFAULT = 2
WEEK_HOURS = 40
DAY_HOURS = 8

_HOURS_TOKEN_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>weeks?|days?|hours?|hrs?|h\b)",
    re.IGNORECASE,
)


def _extract_first_hours_estimate(q4_text: str) -> float | None:
    """Return the first numeric hours estimate found in Q4 text, or None.

    Recognizes `N hours`, `N hour`, `N h`, `N hr`, `N hrs`, `N day`,
    `N days`, `N week`, `N weeks` (case-insensitive). Days multiply by
    8. Weeks multiply by 40. Returns None if no match. Matches in source
    order; the first match wins so "4-8 hours" yields 4 (the proposer's
    lower-bound estimate).
    """
    match = _HOURS_TOKEN_RE.search(q4_text)
    if match is None:
        return None
    raw = float(match.group("num"))
    unit = match.group("unit").lower().rstrip("s")
    if unit in ("h", "hr", "hour"):
        return raw
    if unit == "day":
        return raw * DAY_HOURS
    if unit == "week":
        return raw * WEEK_HOURS
    return raw


def _hours_to_tier(hours: float) -> int:
    """Map an hours estimate to a tier 1-5 with strict less-than boundaries.

    Matches REQ-008 AC-02 hours mapping. 8h falls in Tier 2 (not Tier 3)
    because the boundary is strict: `2 to less than 8 hours = Tier 2`.
    """
    if hours < 2:
        return 1
    if hours < 8:
        return 2
    if hours < 40:
        return 3
    if hours < 160:
        return 4
    return 5


def _entity_count_to_tier(entity_count: int) -> int:
    """Map an entity count to a tier 1-5.

    Matches REQ-008 AC-02 entity mapping. 0 maps to Tier 1 because no
    other tier can absorb it; the proposer should always have at least
    one named entity in Q3+Q4.
    """
    if entity_count <= 1:
        return 1
    if entity_count <= 3:
        return 2
    if entity_count <= 7:
        return 3
    if entity_count <= 15:
        return 4
    return 5


def phases_needed(tier: int) -> int:
    """Return the number of exploring-knowledge-graph phases required at a tier.

    Per REQ-008 AC-05/AC-10: Tier 1-2 runs Phases 1-2 (shallow);
    Tier 3 runs Phases 1-4 (medium); Tier 4-5 runs all 5 phases (deep).
    Used by AC-10 supplemental trigger logic.
    """
    if tier <= 2:
        return 2
    if tier == 3:
        return 4
    return 5


def supplemental_phase_5_warranted(
    provisional_tier: int, actual_tier: int
) -> bool:
    """Return True when Step 3 tier upgrade requires supplemental traversal.

    Per REQ-008 AC-10: supplemental Phase 5 runs when actual_tier
    classified by Step 3 exceeds the ProvisionalTier set at Step 0.5
    AND the additional phases required for actual_tier exceed those
    already run at provisional_tier.
    """
    return (
        actual_tier > provisional_tier
        and phases_needed(actual_tier) > phases_needed(provisional_tier)
    )


def compute_provisional_tier(q4_text: str, entity_count: int) -> int:
    """Compute ProvisionalTier per REQ-008 AC-02.

    Returns max(hours_tier, entity_tier). If Q4 contains no numeric
    hours estimate, hours_tier defaults to Tier 2.
    """
    hours = _extract_first_hours_estimate(q4_text)
    hours_tier = (
        _hours_to_tier(hours)
        if hours is not None
        else PROVISIONAL_TIER_HOURS_DEFAULT
    )
    entity_tier = _entity_count_to_tier(entity_count)
    return max(hours_tier, entity_tier)


def extract_step0_5_block(spec_text: str) -> str:
    """Return the full Step 0.5 block from spec.md.

    The block runs from the Step 0.5 heading to the next horizontal rule
    delimiter that closes it. Raises ValueError if the heading is absent.
    """
    start = spec_text.find(STEP_0_5_HEADING)
    if start == -1:
        raise ValueError(
            f"Step 0.5 heading not found: {STEP_0_5_HEADING!r}"
        )
    after_heading = spec_text[start:]
    end_match = re.search(r"\n---\n", after_heading)
    if end_match is None:
        raise ValueError(
            "Step 0.5 closing delimiter `\\n---\\n` not found"
        )
    return after_heading[: end_match.start()]


def extract_step0_5_subsection(spec_text: str, subsection_heading: str) -> str:
    """Return the body of a named subsection inside the Step 0.5 block.

    `subsection_heading` is the literal heading line, e.g.
    `#### Step 0.5 ProvisionalTier (auto-classified, no user prompt)`.
    The subsection body runs from after the heading to the next
    sibling h4 heading (`\\n#### `), the next h3 heading (`\\n### `),
    the closing horizontal rule (`\\n---\\n`), or end of input,
    whichever comes first. Raises ValueError if the heading is absent.

    Accepts either the full spec.md text or an extracted Step 0.5 block.
    """
    start = spec_text.find(subsection_heading)
    if start == -1:
        raise ValueError(
            f"Step 0.5 subsection not found: {subsection_heading!r}"
        )
    after_heading = spec_text[start + len(subsection_heading):]
    candidates = [
        m.start()
        for m in (
            re.search(r"\n#### ", after_heading),
            re.search(r"\n### ", after_heading),
            re.search(r"\n---\n", after_heading),
        )
        if m is not None
    ]
    end = min(candidates) if candidates else len(after_heading)
    return after_heading[:end]


def extract_step9_block(spec_text: str) -> str:
    """Return the Step 9 numbered-list item including all 9a-9d checks.

    Step 9 is the last top-level numbered item before the
    `## Evaluation Axes` h2 heading.
    """
    step9_match = re.search(
        r"^9\. Task\(subagent_type=\"critic\"\).*?(?=^## Evaluation Axes)",
        spec_text,
        re.DOTALL | re.MULTILINE,
    )
    if step9_match is None:
        raise ValueError("Step 9 block not found in spec.md")
    return step9_match.group(0)


def has_guard_string(spec_text: str) -> bool:
    """Return True if the partial-M2 guard string is still present.

    The guard is introduced in commit 2A and removed in commit 2B. Its
    presence at Step 9 evaluation time means Step 0.5 is in a partial
    state and AC-12 (PriorArtBlock contract) is not yet load-bearing.
    Step 9 check 9d treats this as an automatic FAIL.
    """
    return GUARD_STRING in spec_text


HALT_BLOCK_FIELDS = ("trigger", "check", "evidence", "test_failed", "deferral")
VALID_HALT_TRIGGERS = frozenset({"H6", "H7", "H8", "H9", "H10", "H11"})

_HALT_BLOCK_RE = re.compile(
    r"```step0_5-halt\n(?P<body>.*?)\n```",
    re.DOTALL,
)
_HALT_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_halt_block(text: str) -> dict[str, str]:
    """Parse a fenced `step0_5-halt` block into its 5 fields.

    Validates that the block contains exactly the 5 fields documented
    in REQ-008 AC-09: trigger, check, evidence, test_failed, deferral.
    Returns a dict mapping field name to value. Raises ValueError if
    the block is missing, malformed, or has the wrong field set.

    Used by D8/D10/D11 dynamic-check promotion: tests can validate
    the format of halt blocks emitted by `/spec` runs without the LLM
    in-the-loop.
    """
    match = _HALT_BLOCK_RE.search(text)
    if match is None:
        raise ValueError(
            "no fenced ```step0_5-halt code block found in input"
        )
    body = match.group("body")
    fields = dict(_HALT_FIELD_RE.findall(body))
    missing = set(HALT_BLOCK_FIELDS) - set(fields)
    extra = set(fields) - set(HALT_BLOCK_FIELDS)
    if missing or extra:
        raise ValueError(
            f"halt block field set wrong: missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    if fields["trigger"] not in VALID_HALT_TRIGGERS:
        raise ValueError(
            f"halt trigger {fields['trigger']!r} not in valid set "
            f"{sorted(VALID_HALT_TRIGGERS)}"
        )
    return fields


METRICS_TALLY_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) "
    r"\| (?P<state>pass|fail) "
    r"\| (?P<trigger>none|H\d+) "
    r"\| (?P<check>none|.+)$",
)


def parse_tally_line(line: str) -> dict[str, str]:
    """Parse one STEP-0.5-METRICS.md tally line into its components.

    Returns dict with keys timestamp, state, trigger, check. Raises
    ValueError if the line does not match the canonical format
    `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`.
    Enforces that pass-state lines have trigger=none and check=none;
    fail-state lines have trigger != none.

    Used by D10/D11 dynamic-check promotion.
    """
    match = METRICS_TALLY_RE.match(line.rstrip("\n"))
    if match is None:
        raise ValueError(f"tally line does not match canonical format: {line!r}")
    parts = match.groupdict()
    if parts["state"] == "pass":
        if parts["trigger"] != "none" or parts["check"] != "none":
            raise ValueError(
                "pass-state tally line must have trigger=none and check=none"
            )
    else:
        if parts["trigger"] == "none":
            raise ValueError(
                "fail-state tally line must have a non-none trigger"
            )
    return parts
