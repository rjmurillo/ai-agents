"""Shared parsing for agent reference-loading contract tests."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def read_reference_text(path: str) -> str:
    """Read a repository reference with normalized whitespace."""
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def reference_loading_section(
    text: str, path: str | Path, heading: str = "## Reference Loading"
) -> str:
    """Read the sole loading section from whitespace-normalized Markdown."""
    assert text.count(heading) == 1, f"{path} must carry {heading!r} once"
    rest = text[text.index(heading) + len(heading) :]
    boundary = rest.find(" ## ")
    return rest if boundary == -1 else rest[:boundary]
