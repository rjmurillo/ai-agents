"""Regression pin for Issue #4079: no U+2014 / U+2013 in the shipped trees.

``.claude/rules/universal.md`` MUST NOT item 5 bans U+2014 and U+2013 in all
authored text, including code comments. Both runtime guards filter to
markdown: ``lefthook.yml`` runs ``staged-dashes`` with ``glob: "**/*.md"``
and ``scripts/validation/checks_dash.py`` keeps only paths ending in
``.md``. Python files under ``.claude/skills/*/scripts/`` therefore ship
prohibited dashes inside prompt strings that reach models at runtime, and
nothing catches a regression.

This test is extension-agnostic on purpose: it covers the ``.py`` files the
markdown guards miss. Scope stays on the trees that ship in the
project-toolkit plugin, so widening the staged-file guard repo-wide (117
files across ``tests/``, ``scripts/``, ``build/``) stays a separate change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# Pattern uses Python escapes so this source file itself stays clean of the
# prohibited characters (same convention as tests/evals/test_no_unicode_dashes.py).
_DASH_PATTERN = re.compile(r"[\u2013\u2014]")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Trees shipped in the project-toolkit plugin, plus the committed Serena
# memories the agents read at runtime.
_SCANNED_PREFIXES = (
    ".claude/agents/",
    ".claude/skills/",
    ".serena/memories/",
    "src/copilot-cli/",
)

# universal.md carve-out: these fixtures intentionally carry the prohibited
# bytes to exercise the detection logic.
_EXCLUDED_PREFIXES = ("tests/hooks/fixtures/",)


def is_scanned(path: str) -> bool:
    """Return True when ``path`` belongs to a shipped tree and is not a fixture."""
    if path.startswith(_EXCLUDED_PREFIXES):
        return False
    return path.startswith(_SCANNED_PREFIXES)


def _tracked_paths() -> list[str]:
    """List git-tracked files in the scanned trees."""
    completed = subprocess.run(
        ["git", "ls-files", "-z", *_SCANNED_PREFIXES],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in completed.stdout.split("\0") if p and is_scanned(p)]


def _dash_hits() -> list[str]:
    """Return ``path:lineno`` for every prohibited dash in the scanned trees."""
    hits: list[str] = []
    for rel in _tracked_paths():
        try:
            text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary asset or dangling entry; nothing to police
        hits.extend(
            f"{rel}:{lineno}"
            for lineno, line in enumerate(text.splitlines(), start=1)
            if _DASH_PATTERN.search(line)
        )
    return hits


def test_plugin_trees_have_no_unicode_dashes() -> None:
    """Issue #4079: shipped trees must not contain U+2014 / U+2013."""
    hits = _dash_hits()
    assert not hits, (
        "Unicode dashes (U+2014 / U+2013) found in shipped plugin trees "
        "(Issue #4079). Replace with comma, colon, period, parentheses, or "
        "restructure the sentence. Offending locations: " + ", ".join(hits)
    )


def test_dash_pattern_matches_both_dashes() -> None:
    """Negative control: a broken regex must not make the scan vacuous."""
    assert _DASH_PATTERN.search("\u2014")
    assert _DASH_PATTERN.search("\u2013")
    assert not _DASH_PATTERN.search("plain ASCII - hyphen only")


@pytest.mark.parametrize(
    "path",
    [
        "tests/hooks/fixtures/dashes.md",
        "tests/test_plugin_tree_no_unicode_dashes.py",
        "scripts/validation/checks_dash.py",
        "docs/agent-catalog.md",
    ],
)
def test_out_of_scope_paths_are_excluded(path: str) -> None:
    """Fixtures and unshipped trees stay outside the scan."""
    assert not is_scanned(path)


@pytest.mark.parametrize(
    "path",
    [
        ".claude/agents/qa.md",
        ".claude/skills/planner/scripts/planner.py",
        ".serena/memories/github/github-observations.md",
        "src/copilot-cli/skills/planner/scripts/planner.py",
    ],
)
def test_shipped_paths_are_scanned(path: str) -> None:
    """Every shipped tree, markdown and Python alike, stays in scope."""
    assert is_scanned(path)


def test_scan_covers_python_files() -> None:
    """Re-narrowing the scan to markdown must fail here."""
    collected = _tracked_paths()
    assert any(p.endswith(".py") for p in collected), (
        "scan collected no Python files; the markdown-only guards already "
        "cover .md, so a markdown-only scan here would pin nothing new"
    )
