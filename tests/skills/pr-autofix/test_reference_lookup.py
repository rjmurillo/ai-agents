"""The pr-autofix reference lookup resolves under every shipped install layout.

Review thread on PR 7118: a Codex repository install loads the skill from its
own skill directory and no listed candidate located ``references/`` there. The
first candidate is now the directory beside the loaded SKILL.md, so the lookup
does not depend on a layout name. These tests check that candidate is present
in every rendered copy and that it lands on real files in the real Codex tree.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_TREES = (
    "src/claude/skills/pr-autofix",
    "src/codex/skills/pr-autofix",
    "src/copilot-cli/skills/pr-autofix",
    "src/cursor/skills/pr-autofix",
)
REFERENCES = (
    "post-merge-cleanup.md",
    "merge-check-exit-codes.md",
    "extension-points.md",
)
NEXT_TO_SKILL = "1. `references/` next to this `SKILL.md`"


@pytest.mark.parametrize("tree", SKILL_TREES)
def test_every_reference_ships_next_to_each_skill(tree: str) -> None:
    for name in REFERENCES:
        assert (REPO_ROOT / tree / "references" / name).is_file()


@pytest.mark.parametrize("tree", SKILL_TREES)
def test_every_reference_has_a_read_pointer(tree: str) -> None:
    text = (REPO_ROOT / tree / "SKILL.md").read_text(encoding="utf-8")
    for name in REFERENCES:
        assert f"`references/{name}`" in text


@pytest.mark.parametrize("tree", SKILL_TREES)
def test_next_to_skill_is_the_first_candidate(tree: str) -> None:
    text = (REPO_ROOT / tree / "SKILL.md").read_text(encoding="utf-8")
    assert NEXT_TO_SKILL in text
    assert text.index(NEXT_TO_SKILL) < text.index("2. `${CLAUDE_SKILL_DIR}/references/`")


def test_next_to_skill_resolves_in_the_real_codex_tree() -> None:
    """The Codex project install links to src/codex; resolve beside its SKILL.md."""
    codex_skill = REPO_ROOT.joinpath(".agents", "skills", "pr-autofix", "SKILL.md")
    if not codex_skill.exists():
        pytest.skip("Codex install tree is not bound in this checkout")
    for name in REFERENCES:
        assert (codex_skill.parent / "references" / name).is_file()


@pytest.mark.parametrize("tree", SKILL_TREES)
@pytest.mark.parametrize("layout", ["a/b/pr-autofix", "pr-autofix", "deep/er/x/pr-autofix"])
def test_copied_skill_dir_resolves_in_any_location(tree: str, layout: str, tmp_path: Path) -> None:
    """Negative control for the layout name: a copy anywhere resolves beside SKILL.md."""
    target = tmp_path / layout
    shutil.copytree(REPO_ROOT / tree, target)
    assert (target / "SKILL.md").is_file()
    for name in REFERENCES:
        assert (target / "references" / name).is_file()


def test_a_skill_dir_without_references_resolves_nothing(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("x", encoding="utf-8")
    assert not (tmp_path / "references").exists()
