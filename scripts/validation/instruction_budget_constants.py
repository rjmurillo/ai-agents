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
    # Lowered from 83,000 after issue #4871 rescoped `code-quality` off the
    # always-on corpus. The `.md` corpus measured 56,321 bytes afterward, so
    # this is seeded above it the way the other three are. The ratchet may only
    # fall; `tests/validation/test_instruction_ceiling_ratchet.py` enforces that.
    ".md": 58_000,
}
