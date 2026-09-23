"""Value objects for instruction budget validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstructionFile:
    """A single instruction file with its measured size and scope.

    ``activation`` records why the file entered the always-on budget:
    ``"applyTo"`` for a ``.github/instructions/*.instructions.md`` rule whose
    frontmatter scopes it to every file of a language, or
    ``"skill-description"`` for a ``.claude/skills/*/SKILL.md`` whose
    frontmatter ``description`` declares unconditional loading (issue #4871).
    """

    name: str
    size_bytes: int
    estimated_tokens: int
    patterns: frozenset[str]
    activation: str = "applyTo"


@dataclass(frozen=True)
class ExtensionResult:
    """Always-on budget measurement for one representative extension.

    ``matched_activation`` parallels ``matched_files`` index-for-index
    (``matched_activation[i]`` is why ``matched_files[i]`` entered the
    budget). It defaults to empty so existing direct constructions (tests,
    callers built before issue #4871) keep working; ``format_json`` fills a
    missing entry with ``"applyTo"`` rather than requiring every caller to
    supply it.
    """

    extension: str
    matched_files: tuple[str, ...]
    total_bytes: int
    estimated_tokens: int
    ceiling_bytes: int
    reserve_bytes: int = 0
    matched_activation: tuple[str, ...] = ()

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

