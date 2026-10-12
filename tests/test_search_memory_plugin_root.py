"""Pins the plugin-root form for every shipped search_memory.py reference (issue #6146).

An installed plugin has no `.claude/skills/memory/scripts/` under the consumer's
working directory. A shipped file that names that bare path, or runs it through
`uv run python`, fails for installed users. The portable form is
`python3 "<plugin root fallback>/skills/memory/scripts/search_memory.py"`, where the
fallback is the `COPILOT_PLUGIN_ROOT` then `CLAUDE_PLUGIN_ROOT` then `.claude` chain
(plugin-self-containment.md MUST-2 and MUST-4).

The exec ratchets scan skills only, and only `python3 .claude/skills/...`
invocations. This test covers agent templates, prose mentions, and the
`uv run python` form that no ratchet sees.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_ROOTS = (
    "templates",
    "src/claude",
    "src/copilot-cli",
    ".claude/agents",
    ".claude/skills",
)

# step-0-5-memory-gate.md carries a vendor-portability declaration for a
# documented second-rung resolution order in this toolkit's own checkout.
DECLARED_FILES = frozenset(
    {
        "src/claude/skills/spec/references/step-0-5-memory-gate.md",
        "src/copilot-cli/skills/spec/references/step-0-5-memory-gate.md",
        ".claude/skills/spec/references/step-0-5-memory-gate.md",
    }
)

BARE_PATH = re.compile(r"(?<![\w}/])\.claude/skills/memory/scripts/search_memory\.py")
UV_RUN = re.compile(r"uv run python\s+\S*search_memory\.py")
PORTABLE = (
    '"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
    '/skills/memory/scripts/search_memory.py"'
)


def _shipped_text_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "--", *SHIPPED_ROOTS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    suffixes = {".md", ".tmpl", ".mustache", ".xml"}
    return [
        REPO_ROOT / name
        for name in listing
        if name and Path(name).suffix in suffixes and name not in DECLARED_FILES
    ]


def _offending_lines(pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for path in _shipped_text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    return hits


def test_no_shipped_file_names_the_bare_search_memory_path() -> None:
    assert _offending_lines(BARE_PATH) == []


def test_no_shipped_file_runs_search_memory_through_uv() -> None:
    assert _offending_lines(UV_RUN) == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("python3 .claude/skills/memory/scripts/search_memory.py q", True),
        ("`.claude/skills/memory/scripts/search_memory.py`", True),
        ('test -f ".claude/skills/memory/scripts/search_memory.py"', True),
        (f"python3 {PORTABLE} q", False),
        ("`${CLAUDE_PLUGIN_ROOT:-.claude}/skills/memory/scripts/search_memory.py`", False),
        ("search_memory.py alone", False),
    ],
)
def test_bare_path_pattern_boundaries(line: str, expected: bool) -> None:
    assert bool(BARE_PATH.search(line)) is expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("uv run python .claude/skills/memory/scripts/search_memory.py q", True),
        (f"uv run python {PORTABLE} q", True),
        (f"python3 {PORTABLE} q", False),
    ],
)
def test_uv_run_pattern_boundaries(line: str, expected: bool) -> None:
    assert bool(UV_RUN.search(line)) is expected


def test_the_guarded_reference_files_exist() -> None:
    names = {path.name for path in _shipped_text_files()}
    assert {"quick-start.md", "skill-reference.md", "architect.claude.md.tmpl"} <= names
