"""Constants for instruction budget validation."""

from __future__ import annotations

INSTRUCTIONS_SUBDIR = ".github/instructions"
INSTRUCTION_GLOB = "*.instructions.md"

# Non-regression ratchet ceilings in bytes, seeded just above current measured
# values (see module docstring). Lower these as the corpus shrinks.
DEFAULT_CEILINGS_BYTES: dict[str, int] = {
    ".py": 99_200,
    ".cs": 99_000,
    ".ps1": 99_000,
    ".md": 84_000,
}
