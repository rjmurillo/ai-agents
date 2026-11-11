"""Shared parsing for agent reference-loading contract tests."""

from pathlib import Path


def reference_loading_section(text: str, path: Path, heading: str = "## Reference Loading") -> str:
    """Read the sole loading section from whitespace-normalized Markdown."""
    assert text.count(heading) == 1, f"{path} must carry {heading!r} once"
    rest = text[text.index(heading) + len(heading) :]
    boundary = rest.find(" ## ")
    return rest if boundary == -1 else rest[:boundary]
