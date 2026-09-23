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
    | \bbefore\s+answering\s+(any|every)\s+(questions?|requests?|prompts?|messages?)\b
      (?!\s+(about|on|for|regarding|involving)\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Non-regression ratchet ceilings in bytes, seeded just above current measured
# values (see module docstring). Lower these as the corpus shrinks.
DEFAULT_CEILINGS_BYTES: dict[str, int] = {
    ".py": 99_000,
    ".cs": 99_000,
    ".ps1": 99_000,
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
