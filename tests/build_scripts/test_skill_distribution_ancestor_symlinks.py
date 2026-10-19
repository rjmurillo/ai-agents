"""Tests for ``skill_distribution._skill_source`` and symlinked sources.

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

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)

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


class TestPluginSkillLink:
    """The ADR-119 link ``.claude/skills/<name>`` to ``src/claude/skills/<name>``."""

    def make_link(self, root: Path, name: str, text: str, link_text: str) -> None:
        plugin = root / "src" / "claude" / "skills" / name
        plugin.mkdir(parents=True)
        (plugin / "SKILL.md").write_text(text, encoding="utf-8")
        link = root / ".claude" / "skills" / name
        link.parent.mkdir(parents=True)
        link.symlink_to(link_text, target_is_directory=True)

    def test_exact_adr_119_link_is_read(self, tmp_path: Path) -> None:
        self.make_link(tmp_path, "linked", LOCAL, "../../src/claude/skills/linked")

        assert skill_distribution.is_repo_local(tmp_path, "linked") is True

    def test_link_to_another_skill_is_refused(self, tmp_path: Path) -> None:
        self.make_link(tmp_path, "other", LOCAL, "../../src/claude/skills/other")
        link = tmp_path / ".claude" / "skills" / "linked"
        link.symlink_to("../../src/claude/skills/other", target_is_directory=True)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path, "linked")

    def test_absolute_link_text_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "claude" / "skills" / "linked"
        self.make_link(tmp_path, "linked", LOCAL, str(target))

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path, "linked")

    def test_linked_skill_whose_file_is_a_symlink_is_refused(self, tmp_path: Path) -> None:
        self.make_link(tmp_path, "linked", LOCAL, "../../src/claude/skills/linked")
        outside = tmp_path / "outside.txt"
        outside.write_text(LOCAL, encoding="utf-8")
        skill_md = tmp_path / "src" / "claude" / "skills" / "linked" / "SKILL.md"
        skill_md.unlink()
        skill_md.symlink_to(outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path, "linked")


class TestSymlinkedSources:
    def test_symlinked_installed_skill_md_is_refused_without_reading_it(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("---\nname: SECRET-OUTSIDE: [unclosed\n---\n", encoding="utf-8")
        skill_dir = tmp_path / "repo" / ".claude" / "skills" / "linked"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").symlink_to(outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink") as caught:
            skill_distribution.is_repo_local(tmp_path / "repo", "linked")

        assert "SECRET-OUTSIDE" not in str(caught.value)

    def test_symlinked_template_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text(LOCAL, encoding="utf-8")
        templates = tmp_path / "repo" / "templates" / "skills"
        templates.mkdir(parents=True)
        (templates / "linked.SKILL.md.tmpl").symlink_to(outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path / "repo", "linked")

    def test_symlinked_skill_directory_is_refused(self, tmp_path: Path) -> None:
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "SKILL.md").write_text(LOCAL, encoding="utf-8")
        skills = tmp_path / "repo" / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "linked").symlink_to(outside_dir, target_is_directory=True)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.is_repo_local(tmp_path / "repo", "linked")

    def test_repo_local_names_fails_on_a_symlinked_skill(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text(LOCAL, encoding="utf-8")
        skill_dir = tmp_path / "repo" / ".claude" / "skills" / "linked"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").symlink_to(outside)

        with pytest.raises(skill_distribution.SkillDistributionError, match="symlink"):
            skill_distribution.repo_local_names(tmp_path / "repo")
