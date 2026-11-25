"""Shared fixtures for the adr_reason tests."""

from __future__ import annotations

SHA = "abc1234abc1234abc1234abc1234abc1234abc12"


def full(subject: str, body: str) -> str:
    """The text align's git importer stores (formatCommitAsText in src/lib/git.ts)."""
    parts = [subject]
    if body:
        parts.append(body)
    parts.append("Author: Ada Lovelace")
    parts.append("Date: 2024-05-01T10:00:00Z")
    parts.append("Files changed:\nlib/avoid-prevent-because\ntest/x")
    parts.append(f"URL: https://github.com/o/r/commit/{SHA}")
    return "\n\n".join(parts)
