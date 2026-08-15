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
    ".md": 83_000,
}
