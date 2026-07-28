"""Object id validation shared by git safety gates."""

from __future__ import annotations

ZERO_SHA_LENGTHS = (40, 64)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def is_full_object_id(value: str) -> bool:
    """Return true when ``value`` is a full SHA-1 or SHA-256 hex object id."""

    return len(value) in ZERO_SHA_LENGTHS and all(char in _HEX_DIGITS for char in value)
