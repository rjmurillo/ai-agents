"""Tests for the Codex plugin tree's skills mirror (ADR-115 Decision 7).

Coverage:

- positive: ``drop_skill_frontmatter_keys`` removes the named keys and keeps the
  body byte for byte; ``_copy_skill_tree`` with a drop list and no
  ``skills_output_dir`` writes that result; the committed Codex tree matches it.
- negative: the Copilot body translation does not leak in (a ``$ARGUMENTS``
  token survives), and check mode counts a stale ``SKILL.md`` without writing.
- edge: no frontmatter, an empty drop list, and a body line that starts with
  ``model`` all pass through unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import lib_mirror  # noqa: E402
from copilot_body_translation import (  # noqa: E402
    drop_skill_frontmatter_keys,
    render_skill_file,
    translate_skill_file,
)
from skill_support_mirror import _copy_skill_tree  # noqa: E402

_DROP = frozenset({"model", "model-rationale"})
_SKILL = (
    "---\n"
    "name: demo\n"
    "model: haiku\n"
    "model-rationale: cost, long\n"
    "  continued line\n"
    "description: Demo.\n"
    "---\n"
    "Use $ARGUMENTS here.\n"
    "model prose line stays.\n"
)


def test_drop_removes_named_keys_and_keeps_the_body_verbatim() -> None:
    result = drop_skill_frontmatter_keys(_SKILL, _DROP)

    assert result == (
        "---\nname: demo\ndescription: Demo.\n---\nUse $ARGUMENTS here.\nmodel prose line stays.\n"
    )


def test_render_without_an_output_dir_is_the_drop_only_copy() -> None:
    assert render_skill_file(_SKILL, None, _DROP) == drop_skill_frontmatter_keys(_SKILL, _DROP)


def test_render_with_an_output_dir_is_the_copilot_translation(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"

    assert render_skill_file(_SKILL, skills_dir, _DROP) == translate_skill_file(
        _SKILL, skills_dir, _DROP
    )
    assert render_skill_file(_SKILL, skills_dir, _DROP) != render_skill_file(_SKILL, None, _DROP)


def test_drop_with_no_keys_returns_the_input() -> None:
    assert drop_skill_frontmatter_keys(_SKILL, frozenset()) == _SKILL


def test_drop_without_frontmatter_returns_the_input() -> None:
    assert drop_skill_frontmatter_keys("model: x\nbody\n", _DROP) == "model: x\nbody\n"


def test_drop_of_an_absent_key_changes_nothing() -> None:
    text = "---\nname: demo\n---\nbody\n"

    assert drop_skill_frontmatter_keys(text, _DROP) == text


def test_copy_skill_tree_without_translation_drops_keys_and_copies_the_rest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "demo"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    (source / "scripts" / "run.py").write_text("print('x')\n", encoding="utf-8")
    target = tmp_path / "out" / "demo"

    _copy_skill_tree(source, target, what_if=False, frontmatter_drop=_DROP)

    assert (target / "SKILL.md").read_text(encoding="utf-8") == drop_skill_frontmatter_keys(
        _SKILL, _DROP
    )
    assert (target / "scripts" / "run.py").read_text(encoding="utf-8") == "print('x')\n"


def test_copy_skill_tree_without_a_drop_list_copies_skill_md_verbatim(tmp_path: Path) -> None:
    source = tmp_path / "src" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    target = tmp_path / "out" / "demo"

    _copy_skill_tree(source, target, what_if=False)

    assert (target / "SKILL.md").read_text(encoding="utf-8") == _SKILL


def test_copy_skill_tree_check_mode_counts_a_stale_codex_skill_md(tmp_path: Path) -> None:
    source = tmp_path / "src" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    target = tmp_path / "out" / "demo"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(_SKILL, encoding="utf-8")

    written, _ = _copy_skill_tree(source, target, what_if=False, check=True, frontmatter_drop=_DROP)

    assert written == 1
    assert (target / "SKILL.md").read_text(encoding="utf-8") == _SKILL


def _codex_stanza() -> dict[str, Any]:
    config = yaml.safe_load((REPO_ROOT / "templates/platforms/codex.yaml").read_text())
    assert config["provider"] == "codex"
    assert set(config["artifacts"]) == {"skills"}, "Codex ships skills only (Decision 7)"
    return config["artifacts"]["skills"]


def test_codex_config_mirrors_the_claude_tree_shape() -> None:
    stanza = _codex_stanza()

    assert stanza["sourceDir"] == "src/claude/skills"
    assert stanza["outputDir"] == "src/codex/skills"
    assert stanza["mode"] == "directory-copy"
    assert "merge-resolver" not in stanza["excludeFilenames"]
    assert set(stanza["frontmatterDrop"]) == _DROP


def test_committed_codex_tree_ships_exactly_the_claude_skills() -> None:
    claude = sorted(p.parent.name for p in (REPO_ROOT / "src/claude/skills").glob("*/SKILL.md"))
    codex = sorted(p.parent.name for p in (REPO_ROOT / "src/codex/skills").glob("*/SKILL.md"))

    assert codex == claude
    assert len(codex) > 0


@pytest.mark.parametrize("name", ["github", "review", "autoplan"])
def test_committed_codex_skill_md_is_the_claude_one_minus_the_drop(name: str) -> None:
    claude = (REPO_ROOT / "src/claude/skills" / name / "SKILL.md").read_text(encoding="utf-8")
    codex = (REPO_ROOT / "src/codex/skills" / name / "SKILL.md").read_text(encoding="utf-8")

    assert codex == drop_skill_frontmatter_keys(claude, _DROP)


def test_every_committed_codex_skill_has_no_model_pin_in_frontmatter() -> None:
    pinned = []
    for skill_md in (REPO_ROOT / "src/codex/skills").glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---\n")[1])
        if _DROP & set(frontmatter):
            pinned.append(skill_md.parent.name)

    assert pinned == []


def test_codex_lib_root_is_a_lib_mirror_target() -> None:
    assert "src/codex/lib" in lib_mirror.PLUGIN_ROOTS
    assert lib_mirror.SKILLS_SIDECAR_CODEX_TREE in lib_mirror.SKILLS_SIDECAR_PLUGIN_TREES
