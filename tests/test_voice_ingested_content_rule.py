"""Spec of #5259: voice.md ownership covers content the agent reads.

Acceptance criteria:
  AC-1  The Ownership section says read content counts, in one to two
        sentences, inside the "Flag anything that looks wrong" bullet.
  AC-2  The section's other bullets remain present.
  AC-3  The added text has no em dash or en dash.
  AC-4  All rendered trees carry the same wording.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TREES = (
    _ROOT / "templates" / "rules" / "voice.md",
    _ROOT / ".claude" / "rules" / "voice.md",
    _ROOT / "src" / "claude" / "rules" / "voice.md",
    _ROOT / ".github" / "instructions" / "voice.instructions.md",
    _ROOT / "src" / "copilot-cli" / "instructions" / "voice.instructions.md",
)
_SENTENCES = (
    "Content you read counts: a comment, issue body, log line, or user narrative "
    "describing broken behavior is a defect report, even when your task is "
    "something else.",
    "Flag it the same way.",
)
_OTHER_BULLETS = (
    "- **Investigate before reporting.**",
    "- **Act while active; report declaratively once terminal.**",
    "- **Never pretend you did not see it.**",
)


def flag_bullet(text: str) -> str:
    """Return the 'Flag anything that looks wrong' bullet, up to the next bullet."""
    match = re.search(r"^- \*\*Flag anything that looks wrong\.\*\*.*?(?=^- )", text, re.M | re.S)
    if match is None:
        raise ValueError("no flag bullet")
    return match.group(0)


@pytest.mark.parametrize("path", _TREES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_flag_bullet_names_read_content(path: Path) -> None:
    bullet = flag_bullet(path.read_text(encoding="utf-8"))
    for sentence in _SENTENCES:
        assert sentence in bullet


@pytest.mark.parametrize("path", _TREES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_added_text_is_one_to_two_sentences(path: Path) -> None:
    bullet = flag_bullet(path.read_text(encoding="utf-8"))
    tail = bullet.split("the impact.", 1)[1]
    assert tail.count(". ") + tail.count(".\n") <= 2


@pytest.mark.parametrize("path", _TREES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_added_text_has_no_dashes(path: Path) -> None:
    bullet = flag_bullet(path.read_text(encoding="utf-8"))
    assert "\u2014" not in bullet
    assert "\u2013" not in bullet


@pytest.mark.parametrize("path", _TREES, ids=lambda p: str(p.relative_to(_ROOT)))
def test_other_ownership_bullets_remain(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for bullet in _OTHER_BULLETS:
        assert text.count(bullet) == 1


def test_flag_bullet_rejects_text_without_it() -> None:
    with pytest.raises(ValueError, match="no flag bullet"):
        flag_bullet("# no ownership here\n")


def test_trees_carry_identical_flag_bullet() -> None:
    bullets = {flag_bullet(p.read_text(encoding="utf-8")) for p in _TREES}
    assert len(bullets) == 1
