"""Shared validation result types.

Provides a common ValidationResult dataclass used across validation scripts.
The is_valid property enforces the invariant: a result is valid when errors
is empty. This eliminates manual boolean tracking and prevents inconsistencies
between the error list and a separate validity flag.

Related: Issue #839 (Type Design Improvements)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of a validation operation.

    The is_valid property is derived from the errors list. A result with
    no errors is valid. Warnings do not affect validity.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return True when no errors exist."""
        return len(self.errors) == 0
