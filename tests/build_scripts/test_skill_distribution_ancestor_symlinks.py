"""Tests for ``skill_distribution._skill_source`` and a symlinked ancestor directory.

A symlinked ``.claude/skills`` or ``templates/skills`` would make the flag read,
and a parse error quote, a file outside the skill tree even when the skill's own
file and directory are regular. Split from ``test_skill_distribution.py`` to keep
both files under the 500-line limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT / "build" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import skill_distribution  # noqa: E402

LOCAL = "---\nname: linked\nmetadata:\n  distribution: repo-local\n---\n\nbody\n"


def link_dir(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)


class TestSymlinkedAncestor:
    def test_symlinked_skills_directory_is_refused_without_quoting(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        (outside / "linked").mkdir(parents=True)
        (outside / "linked" / "SKILL.md").write_text(
            "---\nname: linked\nmetadata: *secretalias\n---\n", encoding="utf-8"
        )
        link_dir(tmp_path / "repo" / ".claude" / "skills", outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink") as caught:
            skill_distribution.is_repo_local(tmp_path / "repo", "linked")

        assert "secretalias" not in str(caught.value)

    def test_symlinked_templates_directory_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "linked.SKILL.md.tmpl").write_text(LOCAL, encoding="utf-8")
        link_dir(tmp_path / "repo" / "templates" / "skills", outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path / "repo", "linked")

    def test_repo_local_names_fails_on_a_symlinked_skills_directory(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        (outside / "linked").mkdir(parents=True)
        (outside / "linked" / "SKILL.md").write_text(LOCAL, encoding="utf-8")
        link_dir(tmp_path / "repo" / ".claude" / "skills", outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.repo_local_names(tmp_path / "repo")

    def test_absent_skill_under_a_symlinked_directory_is_not_repo_local(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        link_dir(tmp_path / "repo" / ".claude" / "skills", outside)

        assert skill_distribution.is_repo_local(tmp_path / "repo", "absent") is False

    def test_symlinked_repo_root_is_allowed(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "repo" / ".claude" / "skills" / "linked"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(LOCAL, encoding="utf-8")
        root_link = tmp_path / "repo-link"
        root_link.symlink_to(tmp_path / "repo", target_is_directory=True)

        assert skill_distribution.is_repo_local(root_link, "linked") is True
