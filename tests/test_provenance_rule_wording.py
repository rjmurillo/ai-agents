"""Spec AC-12 of #5698: rule wording that keeps agents from filing found work.

SPEC-agent-backlog-provenance.md AC-12, verbatim:
  builder-ethos.md shall contain the phrases "task selection is not the agent's
  to compress" and "may only flag, never file" (grep count 1 or more for each),
  and voice.md shall contain zero occurrences of "Worth a follow-up issue" and
  at least one occurrence of "PR body" inside its Ownership section.

Checks both rendered trees: .claude/rules and .github/instructions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_ETHOS = (
    _ROOT / ".claude" / "rules" / "builder-ethos.md",
    _ROOT / ".github" / "instructions" / "builder-ethos.instructions.md",
)
_VOICE = (
    _ROOT / ".claude" / "rules" / "voice.md",
    _ROOT / ".github" / "instructions" / "voice.instructions.md",
)
_ETHOS_PHRASES = (
    "task selection is not the agent's to compress",
    "may only flag, never file",
)


def ownership_section(text: str) -> str:
    """Return the body of the '## Ownership' section, up to the next '## ' heading."""
    match = re.search(r"^## Ownership[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        raise ValueError("no Ownership section")
    return match.group(1)


@pytest.mark.parametrize("path", _ETHOS, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("phrase", _ETHOS_PHRASES)
def test_builder_ethos_contains_phrase(path: Path, phrase: str) -> None:
    assert phrase in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", _VOICE, ids=lambda p: p.parent.name)
def test_voice_has_no_follow_up_issue_offer(path: Path) -> None:
    assert "Worth a follow-up issue" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", _VOICE, ids=lambda p: p.parent.name)
def test_voice_ownership_names_pr_body(path: Path) -> None:
    assert "PR body" in ownership_section(path.read_text(encoding="utf-8"))


def test_ownership_section_excludes_later_sections() -> None:
    text = "## Ownership\nin scope\n## Other\nPR body\n"
    assert "PR body" not in ownership_section(text)


def test_ownership_section_missing_raises() -> None:
    with pytest.raises(ValueError):
        ownership_section("## Other\nPR body\n")
