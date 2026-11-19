"""README row and fenced-heading helpers for the agent and skill docs gate.

Split from ``check_agent_skill_docs.py`` so that file stays under the
500-line taste ceiling. The row pattern is the one the skillforge scaffold
copies. A fence closes on the same character, at least as long as the
opening run, with no info string. A shorter inner fence stays inside.
"""

from __future__ import annotations

import re

# Local page only: optional ./, fragment, and title. Not a URL.
# Same pattern as the skillforge docs scaffold.
ROW_LINK = re.compile(
    r"\]\(\s*<?(?:\./)?([A-Za-z0-9_.-]+)\.md(?:#[^>\s)]*)?>?"
    r"(?:\s+(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\([^)\n]*\)))?\s*\)"
)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def readme_rows(readme_text: str) -> set[str]:
    """Return page names linked from Markdown table rows."""
    rows: set[str] = set()
    for line in readme_text.splitlines():
        if line.lstrip().startswith("|"):
            rows.update(ROW_LINK.findall(line))
    return rows


def _fence_run(stripped: str) -> tuple[str, int, str] | None:
    """Return fence character, length, and the remainder of the line."""
    if not stripped or stripped[0] not in "`~":
        return None
    char = stripped[0]
    length = 1
    while length < len(stripped) and stripped[length] == char:
        length += 1
    if length < 3:
        return None
    return char, length, stripped[length:]


def live_headings(text: str) -> dict[int, re.Match[str]]:
    """Return heading matches outside fenced code blocks, keyed by line index."""
    found: dict[int, re.Match[str]] = {}
    fence: tuple[str, int] | None = None
    for index, line in enumerate(text.splitlines()):
        stripped = line.lstrip()
        run = _fence_run(stripped)
        if run is not None:
            char, length, rest = run
            if fence is None:
                fence = (char, length)
            elif char == fence[0] and length >= fence[1] and rest.strip() == "":
                fence = None
            continue
        if fence is None and (match := HEADING.match(line)):
            found[index] = match
    return found


def headings(text: str) -> list[re.Match[str]]:
    """Return heading matches outside fenced code blocks."""
    return list(live_headings(text).values())
