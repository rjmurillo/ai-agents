"""Focused contract tests for the memory-consolidate skill."""

from __future__ import annotations

import re
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    return next(path for path in start.parents if (path / "pyproject.toml").is_file())


def _frontmatter(body: str) -> str:
    match = re.search(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n", body)
    assert match is not None, "SKILL.md must start with frontmatter"
    return match.group(1)


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
REPO_ROOT = _find_repo_root(SKILL_DIR)
MEMORY_README = REPO_ROOT / ".serena" / "memories" / "README.md"
MEMORY_ROUTER_MD = SKILL_DIR.parent / "memory" / "SKILL.md"
BODY = SKILL_MD.read_text(encoding="utf-8")
UNWRAPPED = " ".join(BODY.split())


def test_identity_and_process_contract() -> None:
    frontmatter = _frontmatter(BODY)
    assert SKILL_DIR.name == "memory-consolidate"
    assert re.search(r"^name:\s*memory-consolidate\s*$", frontmatter, re.MULTILINE)
    assert 3 <= len(re.findall(r"`[^`]+`", frontmatter)) <= 5
    assert "durable" in frontmatter.lower()
    assert "dated" in frontmatter.lower()
    assert re.search(r"^\s*adr:.*ADR-056", frontmatter, re.MULTILINE)
    assert len(BODY.splitlines()) <= 500
    for heading in (
        "### Phase 1: Take Stock",
        "### Phase 2: Consolidate",
        "### Phase 3: Tidy the Index",
    ):
        assert re.search(rf"^{re.escape(heading)}$", BODY, re.MULTILINE)


def test_merge_and_date_safety_contract() -> None:
    lower = UNWRAPPED.lower()
    for phrase in (
        "genuine duplicate",
        "distinct atomic concepts",
        "update the survivor first",
        "redirect the index last",
        "restore every touched file",
        "never physically deletes",
        "human-confirmed",
        "source stamp",
        "file history",
        "ambiguous-date",
    ):
        assert phrase in lower
    assert "against the current session date" not in lower
    assert "dangling" in lower
    assert "still exists" in lower or "still on disk" in lower


def test_index_and_discovery_contract() -> None:
    assert MEMORY_README.is_file()
    readme = MEMORY_README.read_text(encoding="utf-8")
    assert "visible in `list_memories`" in readme
    assert "hidden from `list_memories`" in readme
    for phrase in (
        "top-level files only",
        "*-index.md",
        "bounded stale-index audit",
        "dangling index entries as errors",
        "These three tiers govern discovery only",
        "run them regardless of which tier surfaced that list",
        "200 lines",
        "25 KB",
        "own operational budget",
    ):
        assert phrase in UNWRAPPED
    for script in (
        "supersession_sweep.py",
        "count_memory_tokens.py",
        "test_memory_size.py",
    ):
        assert script in BODY


def test_output_and_router_contract() -> None:
    assert BODY.count("## Output") == 1
    for field in ("Success", "Data", "Error", "Metadata"):
        assert f"**{field}**" in BODY
    assert MEMORY_ROUTER_MD.is_file()
    assert "memory-consolidate" in MEMORY_ROUTER_MD.read_text(encoding="utf-8")


def test_repo_root_resolution_is_mirror_safe() -> None:
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert MEMORY_README.is_file()
