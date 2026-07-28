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

    @property
    def usage_percent(self) -> float:
        if self.ceiling_bytes <= 0:
            return 0.0
        return round((self.total_bytes / self.ceiling_bytes) * 100, 1)

    @property
    def over_budget(self) -> bool:
        return self.total_bytes > self.ceiling_bytes

