"""Case-sensitive, segment-aware path globs.

``*`` and ``?`` match within one path segment. ``**`` as a whole segment
matches zero or more segments. Matching never crosses ``/`` otherwise.
"""

from __future__ import annotations

from fnmatch import fnmatchcase


class GlobError(ValueError):
    """Raised when a glob pattern is not a valid repo-relative pattern."""


def validate_glob(pattern: str) -> None:
    """Reject patterns that are empty, absolute, or escape the repository."""
    if not isinstance(pattern, str) or not pattern:
        raise GlobError("glob must be a non-empty string")
    if pattern.startswith("/") or "\\" in pattern:
        raise GlobError(f"glob must be repo-relative with '/' separators: {pattern!r}")
    for segment in pattern.split("/"):
        if segment in ("", ".", ".."):
            raise GlobError(f"glob has an empty or relative segment: {pattern!r}")
        if "**" in segment and segment != "**":
            raise GlobError(f"'**' must be a whole segment: {pattern!r}")


def _match_segments(pattern: list[str], path: list[str]) -> bool:
    if not pattern:
        return not path
    head = pattern[0]
    if head == "**":
        # Zero segments, or consume one path segment and retry.
        if _match_segments(pattern[1:], path):
            return True
        return bool(path) and _match_segments(pattern, path[1:])
    if not path:
        return False
    return fnmatchcase(path[0], head) and _match_segments(pattern[1:], path[1:])


def glob_match(pattern: str, path: str) -> bool:
    """Return True when the repo-relative ``path`` matches ``pattern``."""
    if not path or path.startswith("/"):
        return False
    return _match_segments(pattern.split("/"), path.split("/"))


def any_match(patterns: tuple[str, ...] | list[str], path: str) -> bool:
    """Return True when any pattern matches ``path``."""
    return any(glob_match(pattern, path) for pattern in patterns)
