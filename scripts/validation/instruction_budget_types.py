"""Value objects for instruction budget validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstructionFile:
    """A single instruction file with its measured size and scope."""

    name: str
    size_bytes: int
    estimated_tokens: int
    patterns: frozenset[str]


@dataclass(frozen=True)
class ExtensionResult:
    """Always-on budget measurement for one representative extension."""

    extension: str
    matched_files: tuple[str, ...]
    total_bytes: int
    estimated_tokens: int
    ceiling_bytes: int
    reserve_bytes: int = 0

    @property
    def usage_percent(self) -> float:
        if self.ceiling_bytes <= 0:
            return 0.0
        return round((self.total_bytes / self.ceiling_bytes) * 100, 1)

    @property
    def over_budget(self) -> bool:
        return self.total_bytes > self.ceiling_bytes

    @property
    def headroom_bytes(self) -> int:
        """Bytes still available before the ceiling. Negative once breached."""
        return self.ceiling_bytes - self.total_bytes

    @property
    def under_reserve(self) -> bool:
        """Within the ceiling but with less headroom than the reserve requires.

        A branch measured against its own base can pass while a sibling branch
        also passes, yet their merged result breaches. The reserve is the room
        kept free so those concurrent merges land below the ceiling instead of
        over it.
        """
        if self.reserve_bytes <= 0 or self.over_budget:
            return False
        return self.headroom_bytes < self.reserve_bytes

