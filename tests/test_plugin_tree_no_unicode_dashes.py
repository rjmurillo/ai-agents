"""Regression pin for Issue #4079: no U+2014 / U+2013 in the shipped trees.

``.claude/rules/universal.md`` MUST NOT item 4 bans U+2014 and U+2013 in all
authored text, including code comments. Both runtime guards filter to
markdown: ``lefthook.yml`` runs ``staged-dashes`` with ``glob: "**/*.md"``
and ``scripts/validation/checks_dash.py`` keeps only paths ending in
``.md``. Every non-markdown file in a plugin root therefore ships prohibited
dashes with no gate in the way, and nothing catches a regression.

Scope is the whole of each shipped plugin root, not a hand-picked subset.
``.claude-plugin/marketplace.json`` names ``./.claude`` and ``./src/claude``;
``.github/plugin/marketplace.json`` names ``src/copilot-cli``. An earlier
draft of this pin listed only ``.claude/agents/`` and ``.claude/skills/``,
which left 43 tracked ``.py`` files under ``.claude/hooks/`` and
``.claude/lib/`` uncovered, six of them with no ``src/copilot-cli`` mirror to
catch them indirectly. Widening costs nothing: the same scan over the full
roots reports zero hits.

The committed Serena memories are in scope too. They do not ship in a
plugin, but agents read them at runtime and the markdown guards are the only
thing covering them.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

# Pattern uses Python escapes so this source file itself stays clean of the
# prohibited characters (same convention as tests/evals/test_no_unicode_dashes.py).
_DASH_PATTERN = re.compile(r"[\u2013\u2014]")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The three plugin roots named by the two marketplace manifests, plus the
# committed Serena memories the agents read at runtime.
_SCANNED_PREFIXES = (
    ".claude/",
    "src/claude/",
    "src/copilot-cli/",
    ".serena/memories/",
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
        encoding="utf-8",
        check=True,
    )
    return [p for p in completed.stdout.split("\0") if p and is_scanned(p)]


def dash_hits(paths: Iterable[str], root: Path) -> list[str]:
    """Return ``path:lineno`` for every prohibited dash under ``root``."""
    hits: list[str] = []
    for rel in paths:
        try:
            text = (root / rel).read_text(encoding="utf-8")
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
    hits = dash_hits(_tracked_paths(), _REPO_ROOT)
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


@pytest.mark.parametrize("dash", ["\u2014", "\u2013"])
def test_dash_hits_reports_the_offending_line(tmp_path: Path, dash: str) -> None:
    """Positive control: the scanner finds a planted dash and names its line."""
    planted = tmp_path / "probe.py"
    planted.write_text(f"# clean\n# regression probe {dash} here\n", encoding="utf-8")

    assert dash_hits(["probe.py"], tmp_path) == ["probe.py:2"]


def test_dash_hits_ignores_ascii_punctuation(tmp_path: Path) -> None:
    """Negative case: hyphens and other ASCII punctuation are not hits."""
    clean = tmp_path / "clean.py"
    clean.write_text("# a - b, c: d (e) f/g\n", encoding="utf-8")

    assert dash_hits(["clean.py"], tmp_path) == []


def test_dash_hits_skips_unreadable_entries(tmp_path: Path) -> None:
    """Edge case: a binary blob and a dangling path are skipped, not raised on."""
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00binary")

    assert dash_hits(["blob.bin", "does-not-exist.md"], tmp_path) == []


@pytest.mark.parametrize(
    "path",
    [
        "tests/hooks/fixtures/dashes.md",
        "tests/test_plugin_tree_no_unicode_dashes.py",
        "scripts/validation/checks_dash.py",
        "docs/agent-catalog.md",
        "build/scripts/generate_skills.py",
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
        ".claude/hooks/invoke_dispatch_claude.py",
        ".claude/lib/paths.py",
        ".claude/commands/ship.md",
        ".claude/rules/universal.md",
        "src/claude/qa.md",
        ".serena/memories/github/github-observations.md",
        "src/copilot-cli/skills/planner/scripts/planner.py",
    ],
)
def test_shipped_paths_are_scanned(path: str) -> None:
    """Every shipped tree, markdown and Python alike, stays in scope."""
    assert is_scanned(path)


@pytest.mark.parametrize(
    "prefix",
    [
        ".claude/agents/",
        ".claude/commands/",
        ".claude/hooks/",
        ".claude/lib/",
        ".claude/rules/",
        ".claude/skills/",
        "src/claude/",
        "src/copilot-cli/",
        ".serena/memories/",
    ],
)
def test_scan_reaches_every_shipped_subtree(prefix: str) -> None:
    """Re-narrowing the scan away from any shipped subtree must fail here."""
    collected = _tracked_paths()
    assert any(p.startswith(prefix) for p in collected), (
        f"scan collected no tracked file under {prefix}; the markdown-only "
        "guards do not cover that subtree, so dropping it reopens Issue #4079"
    )


def test_scan_covers_python_files() -> None:
    """Re-narrowing the scan to markdown must fail here."""
    collected = _tracked_paths()
    assert any(p.endswith(".py") for p in collected), (
        "scan collected no Python files; the markdown-only guards already "
        "cover .md, so a markdown-only scan here would pin nothing new"
    )
