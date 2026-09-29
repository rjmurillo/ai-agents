"""Constants for instruction budget validation."""

from __future__ import annotations

import re

INSTRUCTIONS_SUBDIR = ".github/instructions"
INSTRUCTION_GLOB = "*.instructions.md"
DEFAULT_RESERVE_BYTES = 600

# Issue #4871: a skill outside .claude/rules/ can still be effectively
# always-on if its own frontmatter `description` declares unconditional
# loading (for example "Load at the start of EVERY task."). Such a skill is
# behaviorally indistinguishable from a rule matched by a universal `applyTo`,
# so it must count toward the same budget instead of dodging it by living in
# .claude/skills/ rather than .github/instructions/. Matches only the
# `description` field text (checked by the caller), never the skill body:
# body prose like "Every task has a done definition" is not a loading
# instruction and must not trigger this pattern.
# The pattern leans toward over-counting: a router such as autoplan, whose
# description says it routes "any request", is counted because the root
# instructions send most tasks through it.
SKILLS_SUBDIR = ".claude/skills"
SKILL_FILE_NAME = "SKILL.md"
ALWAYS_ON_SKILL_PATTERN: re.Pattern[str] = re.compile(
    r"""
    \b(every|each|any|all)\s+(\w+\s+)?(tasks?|sessions?|turns?|requests?|prompts?|conversations?)\b
    | \balways\s+load(ed)?\b
    | \bload(ed)?\s+first\b
    | \bat\s+(the\s+)?(start\s+of\s+(every|each)|session\s+start)\b
    | \bbefore\s+answering\s+(any|every)\s+((user|incoming|new)\s+)?
      (questions?|requests?|prompts?|messages?)\b
      (?!\s+(about|on|for|regarding|involving|related|concerning)\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Non-regression ratchet ceilings in bytes, seeded just above current measured
# values (see module docstring). Lower these as the corpus shrinks.
DEFAULT_CEILINGS_BYTES: dict[str, int] = {
    ".py": 86_000,
    ".cs": 86_000,
    ".ps1": 86_000,
    # Held at 83,000 deliberately. The rescope in issue #4871 dropped the `.md`
    # corpus to 56,088 bytes, so a lower ceiling is measurable today, but #4871
    # gates the downward ratchet on behavior evidence this repository does not
    # have yet. Its own tracking comments list "Downward budget ratchet after
    # accepted behavior evidence" as still open and state that behavior-changing
    # rescope waits on the #4853 real-CLI evaluator. The probe run for this PR
    # measured runtime membership (which rule files enter the system prompt),
    # not a no-regression before/after on output quality, so it does not clear
    # that gate. Lower this only once the #4853 evaluator produces a frozen
    # before/after for passive repository instructions.
    ".md": 83_000,
}

# Per-fixture activated-bytes ratchet for `instruction_bytes` (issue #5400).
# Each value is the bytes a scripted routing scenario loads on the Claude Code
# path: harness context for the edited path (root and nested guides, scoped
# rules), always-on skills, skill and agent entrypoints, and their capability
# dependencies. F1..F6 are defined in `instruction_bytes_fixtures.FIXTURES`.
# Seeded just above the measured bytes, the same way DEFAULT_CEILINGS_BYTES is.
# Lower a ceiling when a fixture shrinks; never raise one without recording why
# in the same change. `test_instruction_ceiling_ratchet.py` blocks a raise
# against origin/main.
FIXTURE_CEILINGS_BYTES: dict[str, int] = {
    "F1": 276_000,
    "F2": 220_000,
    "F3": 69_000,
    "F4": 90_000,
    "F5": 112_000,
    "F6": 120_000,
}
