"""Constants for instruction budget validation."""

from __future__ import annotations

INSTRUCTIONS_SUBDIR = ".github/instructions"
INSTRUCTION_GLOB = "*.instructions.md"
DEFAULT_RESERVE_BYTES = 600

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
