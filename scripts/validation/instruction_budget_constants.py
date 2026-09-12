"""Constants for instruction budget validation."""

from __future__ import annotations

INSTRUCTIONS_SUBDIR = ".github/instructions"
INSTRUCTION_GLOB = "*.instructions.md"
DEFAULT_RESERVE_BYTES = 600

# Non-regression ratchet ceilings in bytes, seeded just above current measured
# values (see module docstring). Lower these as the corpus shrinks.
DEFAULT_CEILINGS_BYTES: dict[str, int] = {
    # Raised 99_000 -> 100_000 for the three code languages on 2026-09-12.
    # The 99_000 seed predated any code-scoped efficiency rule and left 779
    # bytes of headroom, less than the 600-byte reserve once a 768-byte rule
    # landed, so `.py` failed at 100.0% usage. The rule cannot be scoped
    # around the wall: it ships in the vendored plugin, where this
    # repository's directory layout does not exist, so it must glob on file
    # extension, and extension globs are language-universal by definition.
    # An extension list alone costs 212 bytes against the 179 that were
    # available, so no body size would have fit. Owner decision, taken with
    # the ratchet's purpose and the `.md` evidence precedent below stated.
    # Measured at the raise: `.py` 98_989, `.cs` 97_611, `.ps1` 97_443.
    # This is still a ratchet. Lower all three as the corpus shrinks.
    ".py": 100_000,
    ".cs": 100_000,
    ".ps1": 100_000,
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
