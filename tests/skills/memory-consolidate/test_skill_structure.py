"""Contract tests for the memory-consolidate skill."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "memory-consolidate"
SKILL_MD = SKILL_DIR / "SKILL.md"
MIRROR_MD = REPO_ROOT / "src" / "copilot-cli" / "skills" / "memory-consolidate" / "SKILL.md"
MEMORY_ROUTER_MD = SKILL_DIR.parent / "memory" / "SKILL.md"
BODY = SKILL_MD.read_text(encoding="utf-8")
UNWRAPPED = " ".join(BODY.split())


def _frontmatter() -> str:
    match = re.search(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n", BODY)
    assert match is not None
    return match.group(1)


def test_identity_process_and_mirror() -> None:
    frontmatter = _frontmatter()
    assert re.search(r"^name:\s*memory-consolidate\s*$", frontmatter, re.MULTILINE)
    assert "ADR-" not in BODY
    assert ".agents/" not in BODY
    assert len(BODY.splitlines()) <= 300
    for heading in (
        "### Phase 1: Take Stock",
        "### Phase 2: Consolidate",
        "### Phase 3: Tidy the Index",
    ):
        assert re.search(rf"^{re.escape(heading)}$", BODY, re.MULTILINE)
    assert MIRROR_MD.read_text(encoding="utf-8") == BODY


def test_consolidation_contract() -> None:
    lower = UNWRAPPED.lower()
    for phrase in (
        "genuine duplicate",
        "distinct atomic concepts",
        "delete the poorer file",
        "update the index last",
        "recoverable from git",
        "git status --short -- .serena/memories",
        "git ls-files --error-unmatch",
        "confirming serena is active on the repository",
        "source stamp",
        "trustworthy file history",
        "bulk import",
        "ambiguous-date",
    ):
        assert phrase in lower
    assert "against the current session date" not in lower


def test_discovery_index_and_output_contract() -> None:
    for phrase in (
        "top-level files only",
        "*-index.md",
        "bounded stale-index audit",
        "dangling index entries as errors",
        "200 lines",
        "25 KB",
        "Number of files scanned, changed, and deleted",
        "Final index line count and byte size",
    ):
        assert phrase in UNWRAPPED
    assert "memory-consolidate" in MEMORY_ROUTER_MD.read_text(encoding="utf-8")
