"""Parser-side implementation of REQ-017 Step 0.5 Memory-First Gate.

Refs #1951. Used by `tests/commands/test_spec_step0_5.py`. Implements the
ProvisionalTier computation defined in REQ-017 AC-02 as Python so the
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

import json
import re
from pathlib import Path

# Repo-relative path to the alias table consumed by normalize rule 5. Mirrors
# the path documented in `.claude/commands/spec.md`, subsection
# `#### Step 0.5 topic extraction`, rule 5 (Issue #1978).
SPEC_ENTITY_ALIASES_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "dictionaries"
    / "spec-entity-aliases.json"
)

STEP_0_5_HEADING = "### Step 0.5: Memory-First Gate (blocking, runs after Step 0)"
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
    8. Weeks multiply by 40. Returns None if no match.

    The regex requires the number to be IMMEDIATELY ADJACENT to a unit
    keyword (with optional whitespace). For range expressions like
    "4-8 hours", only the second number ("8") qualifies because "4" is
    followed by `-`, not whitespace or a unit. Tier-classification then
    picks the higher (more conservative) bound, which is acceptable for
    a provisional estimate that Step 3 may revise upward.
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
    """Map an hours estimate to a tier 1-5 with strict less-than upper bounds.

    Matches REQ-017 AC-02 hours mapping. Upper bounds are strict: Tier 2
    range is `2 to less than 8 hours`, so 8h falls in Tier 3 (range
    `8 to less than 40 hours`), NOT Tier 2. The mapping table is the
    canonical source.
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

    Matches REQ-017 AC-02 entity mapping. 0 maps to Tier 1 because no
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


_SEPARATOR_RUN_RE = re.compile(r"[\s\-_]+")
_LEADING_PATH_DOTS_RE = re.compile(r"^[/\\.]+")


def normalize_topic(raw: str) -> str:
    """Normalize a topic or entity name per the spec.md four-rule contract.

    Mirrors the canonical normalization defined in
    `.claude/commands/spec.md`, subsection `#### Step 0.5 topic extraction`,
    quoted verbatim:

        1. Trim leading and trailing whitespace.
        2. Strip leading path separators (`/`, `\\`) AND leading dots (`.`).
        3. Lowercase the string.
        4. Collapse internal separator runs (whitespace, `-`, `_`) to a single
           hyphen, so `spec pipeline`, `spec-pipeline`, and `spec_pipeline`
           all normalize to `spec-pipeline`.

    The same normalization is applied to BOTH the discovered entity name and
    the Q1+Q3+Q4 answers before matching (per `#### Step 0.5 entity
    adjudication`). Returns the normalized hyphen-joined string. An all-
    separator or empty input normalizes to the empty string.
    """
    trimmed = raw.strip()
    stripped = _LEADING_PATH_DOTS_RE.sub("", trimmed)
    lowered = stripped.lower()
    collapsed = _SEPARATOR_RUN_RE.sub("-", lowered)
    return collapsed.strip("-")


def load_entity_aliases(path: Path | None = None) -> dict[str, str]:
    """Load the Step 0.5 entity-alias table as an alias->canonical mapping.

    Reads `.agents/dictionaries/spec-entity-aliases.json` (or `path` when given)
    and returns its `aliases` object. Implements the lookup side of rule 5 in
    `.claude/commands/spec.md`, subsection `#### Step 0.5 topic extraction`.
    Returns an empty dict when the file or the `aliases` key is absent so a
    missing table degrades to a pass-through rather than an error.
    """
    target = path if path is not None else SPEC_ENTITY_ALIASES_PATH
    if not target.is_file():
        return {}
    data = json.loads(target.read_text(encoding="utf-8"))
    aliases = data.get("aliases")
    if not isinstance(aliases, dict):
        return {}
    return {str(k): str(v) for k, v in aliases.items()}


def normalize_topic_with_aliases(
    raw: str, aliases: "dict[str, str] | None" = None
) -> str:
    """Normalize a topic, then apply the rule-5 alias substitution.

    Runs `normalize_topic` (rules 1-4), then looks the result up in the alias
    table (rule 5). On an exact match the canonical value is returned; on a miss
    the rule-4 result is returned unchanged. `aliases` may be passed to avoid
    repeated file reads; when None the table is loaded from the canonical path.

    Mirrors `.claude/commands/spec.md`, subsection `#### Step 0.5 topic
    extraction`, rule 5: "Look up the result of rule 4 ... On a hit, substitute
    the canonical value; on a miss, keep the rule-4 result unchanged."
    """
    normalized = normalize_topic(raw)
    table = aliases if aliases is not None else load_entity_aliases()
    return table.get(normalized, normalized)


def _tokenize_normalized(normalized: str) -> list[str]:
    """Split a normalized hyphen-joined string into its token sequence.

    Per `#### Step 0.5 entity adjudication`: because normalization rule 4
    collapses every whitespace, `-`, and `_` run to a single hyphen, each
    normalized answer is one hyphen-joined string; split it on `-` to recover
    its token sequence. Returns an empty list for the empty string.
    """
    if not normalized:
        return []
    return normalized.split("-")


def entity_matches_answer(entity_name: str, answer: str) -> bool:
    """Return True when a discovered entity matches a Q answer by whole-token equality.

    Mirrors the auto-mode adjudication rule in `.claude/commands/spec.md`,
    subsection `#### Step 0.5 entity adjudication`. Both inputs are normalized
    with `normalize_topic`, then tokenized on `-`. The entity matches the
    answer only when the entity's normalized token sequence appears as a
    contiguous run of whole tokens inside the answer's token sequence:

    - A single-token entity matches only a standalone token.
    - A multi-token entity matches only a contiguous token run.

    This is whole-token equality, NOT substring match. It closes the
    CWE-863 substring bypass: a token-rich answer like
    `auth-service payment-service billing-service` does NOT match a discovered
    `service-mesh` (the `service mesh` token pair never appears contiguously),
    but DOES match `auth-service`.

    An empty entity name never matches (no tokens to match). An empty answer
    matches nothing.

    Stricter/looser/different than canonical: identical to the spec.md
    rule. The spec.md prose is the runtime contract enforced by the LLM;
    this function pins the same semantics deterministically so #1973's
    behavioral tests run without an LLM in the loop.
    """
    entity_tokens = _tokenize_normalized(normalize_topic(entity_name))
    answer_tokens = _tokenize_normalized(normalize_topic(answer))
    if not entity_tokens:
        return False
    span = len(entity_tokens)
    for start in range(0, len(answer_tokens) - span + 1):
        if answer_tokens[start:start + span] == entity_tokens:
            return True
    return False


def adjudicate_entity_scope(entity_name: str, q_answers: "list[str] | tuple[str, ...]") -> str:
    """Classify a discovered entity as `in-scope` or `blast-radius` in auto-mode.

    Mirrors the auto-mode resolution in `.claude/commands/spec.md`,
    subsection `#### Step 0.5 entity adjudication`: a whole-token match
    against ANY of the Q answers resolves the entity as `in-scope`; no match
    resolves it as `blast-radius` (the conservative default). `out-of-scope`
    is a human-only classification (the proposer deliberately excludes the
    entity) and is never produced by auto-mode, so it is not returned here.

    `q_answers` is the list of Step 0 Q1+Q3+Q4 answer strings.
    """
    for answer in q_answers:
        if entity_matches_answer(entity_name, answer):
            return "in-scope"
    return "blast-radius"


def phases_needed(tier: int) -> int:
    """Return the number of exploring-knowledge-graph phases required at a tier.

    Per REQ-017 AC-05/AC-10: Tier 1-2 runs Phases 1-2 (shallow);
    Tier 3 runs Phases 1-4 (medium); Tier 4-5 runs all 5 phases (deep).
    Used by AC-10 supplemental trigger logic.
    """
    if tier <= 2:
        return 2
    if tier == 3:
        return 4
    return 5


def supplemental_traversal_warranted(
    provisional_tier: int, actual_tier: int
) -> bool:
    """Return True when Step 3 tier upgrade requires supplemental traversal.

    Per REQ-017 AC-10: supplemental traversal runs when actual_tier
    classified by Step 3 exceeds the ProvisionalTier set at Step 0.5
    AND the additional phases required for actual_tier exceed those
    already run at provisional_tier. The trigger fires for any tier
    upgrade that crosses a phase boundary, not only Phase 5: Tier 2 ->
    Tier 3 fires (Phases 3-4); Tier 3 -> Tier 4 fires (Phase 5 alone);
    Tier 2 -> Tier 4 fires (Phases 3-5).
    """
    return (
        actual_tier > provisional_tier
        and phases_needed(actual_tier) > phases_needed(provisional_tier)
    )


def compute_provisional_tier(q4_text: str, entity_count: int) -> int:
    """Compute ProvisionalTier per REQ-017 AC-02.

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


def _is_fence_line(stripped: str) -> tuple[str, int] | None:
    """Return (fence_char, run_length) if the line opens or closes a fence.

    A fence is a run of three or more backticks or tildes at the start of the
    (already left-stripped) line. Returns None for any other line.
    """
    for ch in ("`", "~"):
        run = 0
        for c in stripped:
            if c == ch:
                run += 1
            else:
                break
        if run >= 3:
            return ch, run
    return None


def _block_boundary_offset(after_heading: str) -> int:
    """Return the offset where the Step 0.5 block ends, respecting code fences.

    The block terminates at the first line that, OUTSIDE any code fence, is one
    of: a bare horizontal rule (`---`), a sibling h3 (`### `), or an h2 (`## `).
    Heading-shaped and rule-shaped lines INSIDE a fenced code block (for example
    the `### Direct prior art from memory` lines and any `---` inside the
    PriorArtBlock schema example) do not terminate the block. The Step 0.5
    heading itself is skipped: the search starts after the first newline so the
    opening `### Step 0.5 ...` line never matches the h3 boundary.

    Tracks the OPENING fence run length so a four-backtick outer fence stays open
    across an inner three-backtick block (CommonMark: a closing fence uses the
    same character and at least as many of them as the opening fence).

    Returns the length of `after_heading` when no boundary is found, so the block
    runs to end of input.
    """
    fence_char: str | None = None
    fence_len = 0
    offset = 0
    first_line = True
    for line in after_heading.splitlines(keepends=True):
        if first_line:
            first_line = False
            offset += len(line)
            continue
        fence = _is_fence_line(line.lstrip())
        if fence is not None:
            ch, run = fence
            if fence_char is None:
                fence_char = ch
                fence_len = run
            elif fence_char == ch and run >= fence_len:
                fence_char = None
                fence_len = 0
            offset += len(line)
            continue
        if fence_char is None and (
            line.startswith("### ")
            or line.startswith("## ")
            or line.rstrip("\n").rstrip() == "---"
        ):
            return offset
        offset += len(line)
    return len(after_heading)


def extract_step0_5_block(spec_text: str) -> str:
    """Return the full Step 0.5 block from spec.md.

    The block runs from the Step 0.5 heading to its closing boundary: the first
    bare horizontal rule (`---`), sibling h3 (`### `), or h2 (`## `) that appears
    OUTSIDE a code fence. Anchoring on the next sibling boundary (not only a
    literal `\\n---\\n`) hardens the parser against prose churn: a horizontal
    rule inserted inside a fenced example no longer truncates the block early,
    and a stray sibling heading terminates it instead of over-running to the next
    `---`. Raises ValueError if the heading is absent.
    """
    start = spec_text.find(STEP_0_5_HEADING)
    if start == -1:
        raise ValueError(
            f"Step 0.5 heading not found: {STEP_0_5_HEADING!r}"
        )
    after_heading = spec_text[start:]
    end = _block_boundary_offset(after_heading)
    return after_heading[:end]


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
    # Walk line-by-line and track triple-backtick fences so heading-shaped
    # lines inside fenced code blocks (e.g., `### Direct prior art from
    # memory` inside the PriorArtBlock schema example) do not prematurely
    # close the subsection. (?m)^ alone does not solve this: fenced lines
    # also begin at line-start, so an anchored regex still matches them.
    end = len(after_heading)
    # Track the OPENING fence character count so a 4-backtick outer
    # fence stays open across an inner 3-backtick block (CommonMark:
    # closing fence must use the same character and at least as many
    # of them as the opening fence). Spec.md uses ```` outer wrappers
    # for halt-block examples that embed ``` inner blocks.
    fence_char: str | None = None
    fence_len = 0
    offset = 0
    for line in after_heading.splitlines(keepends=True):
        fence = _is_fence_line(line.lstrip())
        if fence is not None:
            ch, run = fence
            if fence_char is None:
                fence_char = ch
                fence_len = run
            elif fence_char == ch and run >= fence_len:
                fence_char = None
                fence_len = 0
            offset += len(line)
            continue
        if fence_char is None and (
            line.startswith("#### ")
            or line.startswith("### ")
            or line.rstrip("\n").rstrip() == "---"
        ):
            end = offset
            break
        offset += len(line)
    return after_heading[:end]


def extract_step9_block(spec_text: str) -> str:
    """Return the Step 9 numbered-list item including all 9a-9d checks.

    Step 9 is the last top-level numbered item before the
    `## Evaluation Axes` h2 heading. The opener is anchored on `^9. ` (any
    step-9 opening line), not the specific `Task(subagent_type="critic")`
    wording, so rephrasing the step's first sentence does not break the
    extractor.
    """
    step9_match = re.search(
        r"^9\. .*?(?=^## Evaluation Axes)",
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
_HALT_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$")


def parse_halt_block(text: str) -> dict[str, str]:
    """Parse a fenced `step0_5-halt` block into its 5 fields.

    Validates strictly:
    - Block contains EXACTLY one fenced ```step0_5-halt section.
    - Body contains EXACTLY 5 non-empty lines.
    - Each line matches `key: value` exactly (no continuation, no
      duplicate keys).
    - Field set is exactly the 5 names documented in REQ-017 AC-09:
      trigger, check, evidence, test_failed, deferral.
    - `trigger` is one of the canonical H6-H11 IDs.

    Returns a dict mapping field name to value. Raises ValueError if
    any of the above conditions fails.

    Used by D8/D10/D11 dynamic-check promotion: tests can validate
    the format of halt blocks emitted by `/spec` runs without the LLM
    in-the-loop.
    """
    matches = list(_HALT_BLOCK_RE.finditer(text))
    if len(matches) == 0:
        raise ValueError(
            "no fenced ```step0_5-halt code block found in input"
        )
    if len(matches) > 1:
        raise ValueError(
            f"input contains {len(matches)} step0_5-halt blocks; "
            "exactly 1 is required"
        )
    body = matches[0].group("body")
    raw_lines = [line for line in body.splitlines() if line.strip()]
    if len(raw_lines) != len(HALT_BLOCK_FIELDS):
        raise ValueError(
            f"halt block must have exactly {len(HALT_BLOCK_FIELDS)} "
            f"non-empty lines; got {len(raw_lines)}"
        )
    fields: dict[str, str] = {}
    for line in raw_lines:
        m = _HALT_FIELD_RE.match(line)
        if m is None:
            raise ValueError(f"halt block line is not `key: value`: {line!r}")
        key, value = m.group(1), m.group(2)
        if key in fields:
            raise ValueError(f"halt block has duplicate key: {key!r}")
        fields[key] = value
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
        if parts["trigger"] not in VALID_HALT_TRIGGERS:
            raise ValueError(
                f"tally trigger {parts['trigger']!r} not in valid set "
                f"{sorted(VALID_HALT_TRIGGERS)}"
            )
    return parts
