"""Tests for the ``metadata.distribution`` skill flag.

A template with ``metadata: distribution: repo-local`` renders only to
``.claude/skills/<name>/`` and reaches no vendor plugin tree. An absent field
means shipped; any other value is a hard error. Covers
``build/scripts/skill_distribution.py`` and the stages that read it:
``skill_templates``, ``skill_support_mirror``, ``generate_skills``, and
``binplace_manifest``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import binplace_manifest  # noqa: E402
import generate_skills  # noqa: E402
import skill_distribution  # noqa: E402
import skill_support_mirror  # noqa: E402
import skill_templates  # noqa: E402
from _skill_template_helpers import (  # noqa: E402
    install_target,
    minimal_platform_config,
    target,
    write_template,
)

needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)

LOCAL = "---\nname: {name}\nmetadata:\n  distribution: repo-local\n---\n\nbody {name}\n"
SHIPPED = "---\nname: {name}\nmetadata:\n  capability:\n    kind: x\n---\n\nbody {name}\n"
BINPLACE_MANIFEST = (
    'schemaVersion: "1.0"\n'
    "provider: claude\n"
    "rows:\n"
    "  - class: skills\n"
    "    source: templates/skills\n"
    "    plugin_tree: src/claude/skills\n"
    "    install_tree: .claude/skills\n"
    "    compile: skill_templates\n"
    "    link: true\n"
)


def seed_skill(repo: Path, name: str, body: str) -> None:
    """Write a template plus the skill's real directory (ADR-119).

    A repo-local skill's real directory is ``.claude/skills/<name>/``. A
    shipped skill's is ``src/claude/skills/<name>/``; ``.claude/skills/<name>``
    is a symlink to it, which these fixtures stand in for with a real
    directory holding the same support file.
    """
    write_template(repo, name, body.format(name=name))
    dirs = [repo / ".claude" / "skills" / name]
    if "distribution: repo-local" not in body:
        dirs.append(repo / "src" / "claude" / "skills" / name)
    for skill_dir in dirs:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "helper.py").write_text("print('support')\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    seed_skill(tmp_path, "local-skill", LOCAL)
    seed_skill(tmp_path, "shipped-skill", SHIPPED)
    return tmp_path


class TestDistributionOfText:
    def test_repo_local_value_is_repo_local(self) -> None:
        assert skill_distribution.distribution_of_text(LOCAL.format(name="x"), "x") == "repo-local"

    def test_absent_field_means_shipped(self) -> None:
        assert skill_distribution.distribution_of_text(SHIPPED.format(name="x"), "x") == "shipped"

    @pytest.mark.parametrize(
        "text",
        [
            "no frontmatter at all\n",
            "---\nname: x\n---\n",
            "---\nname: x\nmetadata: just-a-string\n---\n",
            "---\n- a\n- b\n---\n",
        ],
    )
    def test_missing_or_non_mapping_metadata_means_shipped(self, text: str) -> None:
        assert skill_distribution.distribution_of_text(text, "x") == "shipped"

    @pytest.mark.parametrize("value", ["repo_local", "Repo-Local", "shipped", "''", "null", "true"])
    def test_unknown_value_is_a_hard_error(self, value: str) -> None:
        text = f"---\nname: x\nmetadata:\n  distribution: {value}\n---\n"
        with pytest.raises(skill_distribution.SkillDistributionError, match="distribution"):
            skill_distribution.distribution_of_text(text, "x.tmpl")

    @pytest.mark.parametrize("value", ["[repo-local]", "{a: b}", "[1, 2]"])
    def test_list_or_mapping_value_is_a_hard_error_not_a_type_error(self, value: str) -> None:
        text = f"---\nname: x\nmetadata:\n  distribution: {value}\n---\n"
        with pytest.raises(skill_distribution.SkillDistributionError, match="distribution"):
            skill_distribution.distribution_of_text(text, "x.tmpl")

    def test_empty_value_is_a_hard_error(self) -> None:
        text = "---\nname: x\nmetadata:\n  distribution:\n---\n"
        with pytest.raises(skill_distribution.SkillDistributionError):
            skill_distribution.distribution_of_text(text, "x.tmpl")

    def test_unparseable_frontmatter_is_a_hard_error(self) -> None:
        with pytest.raises(skill_distribution.SkillDistributionError, match="unparseable"):
            skill_distribution.distribution_of_text("---\nname: [unclosed\n---\n", "x.tmpl")

    def test_unparseable_error_names_the_position_not_the_source_line(self) -> None:
        secret = "SECRET-LINE-FROM-ANOTHER-FILE"
        text = f"---\nname: {secret}: [unclosed\n---\n"

        with pytest.raises(skill_distribution.SkillDistributionError) as caught:
            skill_distribution.distribution_of_text(text, "x.tmpl")

        message = str(caught.value)
        assert "frontmatter line 1" in message
        assert secret not in message

    def test_unparseable_error_bounds_the_parser_problem_text(self) -> None:
        text = "---\nname: !!" + "t" * 500 + " value\n---\n"

        with pytest.raises(skill_distribution.SkillDistributionError) as caught:
            skill_distribution.distribution_of_text(text, "x.tmpl")

        assert len(str(caught.value)) < 300


class TestRegularSources:
    def test_regular_files_still_resolve(self, repo: Path) -> None:
        assert skill_distribution.is_repo_local(repo, "local-skill") is True
        assert skill_distribution.is_repo_local(repo, "shipped-skill") is False


class TestResolution:
    def test_template_flag_wins_over_installed_skill_md(self, repo: Path) -> None:
        installed = repo / ".claude" / "skills" / "local-skill" / "SKILL.md"
        installed.write_text(SHIPPED.format(name="local-skill"), encoding="utf-8")

        assert skill_distribution.is_repo_local(repo, "local-skill") is True

    def test_installed_skill_md_is_the_fallback_without_a_template(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "orphan"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(LOCAL.format(name="orphan"), encoding="utf-8")

        assert skill_distribution.is_repo_local(tmp_path, "orphan") is True

    def test_unknown_skill_is_not_repo_local(self, tmp_path: Path) -> None:
        assert skill_distribution.is_repo_local(tmp_path, "ghost") is False

    def test_repo_local_names_lists_only_flagged_skills(self, repo: Path) -> None:
        assert skill_distribution.repo_local_names(repo) == frozenset({"local-skill"})

    def test_repo_local_names_raises_on_a_bad_value(self, repo: Path) -> None:
        write_template(repo, "typo", "---\nname: typo\nmetadata:\n  distribution: local\n---\n")

        with pytest.raises(skill_distribution.SkillDistributionError):
            skill_distribution.repo_local_names(repo)


class TestCompile:
    def test_repo_local_renders_only_to_the_install_tree(self, repo: Path) -> None:
        result = skill_templates.compile_all(repo, validate=False)

        assert result.exit_code == 0
        assert (
            install_target(repo, "local-skill")
            .read_text(encoding="utf-8")
            .endswith("body local-skill\n")
        )
        assert not (repo / "src" / "claude" / "skills" / "local-skill").exists()

    def test_shipped_skill_still_renders_to_the_plugin_tree(self, repo: Path) -> None:
        skill_templates.compile_all(repo, validate=False)

        assert target(repo, "shipped-skill").is_file()
        assert not install_target(repo, "shipped-skill").exists()

    def test_validate_mode_reports_repo_local_drift_at_the_install_tree(self, repo: Path) -> None:
        skill_templates.compile_all(repo, validate=False)
        install_target(repo, "local-skill").write_text("hand edit\n", encoding="utf-8")

        result = skill_templates.compile_all(repo, validate=True)

        assert result.exit_code == 1
        assert result.drifted == [str(install_target(repo, "local-skill"))]

    def test_validate_mode_is_clean_after_a_write(self, repo: Path) -> None:
        skill_templates.compile_all(repo, validate=False)

        assert skill_templates.compile_all(repo, validate=True).exit_code == 0

    def test_owned_targets_hold_only_the_path_compile_writes(self, repo: Path) -> None:
        owned = skill_templates.owned_targets(repo)

        assert install_target(repo, "local-skill") in owned
        assert target(repo, "local-skill") not in owned
        # Shipped: the install path is a symlink, never written through.
        assert target(repo, "shipped-skill") in owned
        assert install_target(repo, "shipped-skill") not in owned

    def test_unknown_distribution_value_fails_compile_with_exit_2(self, repo: Path) -> None:
        seed_skill(repo, "typo", "---\nname: {name}\nmetadata:\n  distribution: local\n---\n")

        result = skill_templates.compile_all(repo, validate=False)

        assert result.exit_code == 2
        assert "typo" not in skill_templates.discover(repo)

    def test_repo_local_skill_md_symlink_is_refused(self, repo: Path, tmp_path_factory) -> None:
        outside = tmp_path_factory.mktemp("outside") / "elsewhere.md"
        outside.write_text("x\n", encoding="utf-8")
        link = install_target(repo, "local-skill")
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks unavailable")

        assert any("is a symlink" in err for err in skill_templates.discover_errors(repo))


class TestMirrors:
    def test_claude_support_sync_leaves_shipped_and_repo_local_trees_alone(
        self, repo: Path
    ) -> None:
        for name in ("local-skill", "shipped-skill"):
            (repo / ".claude" / "skills" / name / "SKILL.md").write_text("x\n", encoding="utf-8")

        written, removed, skipped, errors = generate_skills.prune_stale_claude_skill_support(repo)

        assert (errors, written, removed, skipped) == ([], 0, 0, 0)
        assert (repo / "src/claude/skills/shipped-skill/helper.py").is_file()
        assert not (repo / "src" / "claude" / "skills" / "local-skill").exists()

    def test_claude_support_mirror_reports_a_bad_value(self, repo: Path) -> None:
        write_template(repo, "typo", "---\nname: typo\nmetadata:\n  distribution: local\n---\n")

        _written, _removed, _skipped, errors = generate_skills.prune_stale_claude_skill_support(
            repo
        )

        assert errors
        assert "distribution" in errors[0]

    def test_iter_skill_sources_honors_skip_names(self, repo: Path) -> None:
        for name in ("local-skill", "shipped-skill"):
            (repo / ".claude" / "skills" / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        source = repo / ".claude" / "skills"

        kept = generate_skills._iter_skill_sources(source, set(), frozenset({"local-skill"}))

        assert [p.name for p in kept] == ["shipped-skill"]

    def test_copilot_mirror_skips_repo_local(self, repo: Path) -> None:
        skill_templates.compile_all(repo, validate=False)
        for name in ("local-skill", "shipped-skill"):
            (repo / ".claude" / "skills" / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        config = minimal_platform_config(repo)

        rc = generate_skills.generate_skills(config, repo)

        assert rc == 0
        assert (repo / "out" / "skills" / "shipped-skill" / "helper.py").is_file()
        assert not (repo / "out" / "skills" / "local-skill").exists()

    def test_copilot_mirror_exits_2_on_a_bad_value(self, repo: Path) -> None:
        write_template(repo, "typo", "---\nname: typo\nmetadata:\n  distribution: local\n---\n")
        (repo / ".claude" / "skills" / "shipped-skill" / "SKILL.md").write_text("x\n")

        assert generate_skills.generate_skills(minimal_platform_config(repo), repo) == 2


def seed_vendor_copy(root: Path, name: str) -> Path:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("old\n", encoding="utf-8")
    (skill_dir / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    return skill_dir


class TestStaleVendorCopies:
    """A shipped skill that becomes repo-local must not leave a vendor copy behind."""

    def test_sync_removes_the_stale_claude_plugin_copy(self, repo: Path) -> None:
        tree = repo / "src" / "claude" / "skills"
        stale = seed_vendor_copy(tree, "local-skill")
        kept = seed_vendor_copy(tree, "shipped-skill")

        _written, removed, _skipped, errors = generate_skills.prune_stale_claude_skill_support(repo)

        assert errors == []
        # Only local-skill's two files go. ADR-119: the plugin tree is the only
        # copy of a shipped skill's support files, so shipped-skill's
        # scripts/run.py (no longer mirrored from .claude) must survive.
        assert removed == 2
        assert not stale.exists()
        assert (kept / "scripts" / "run.py").read_text(encoding="utf-8") == "print(1)\n"
        assert (kept / "SKILL.md").read_text(encoding="utf-8") == "old\n"

    def test_sync_check_reports_but_keeps_the_stale_copy(self, repo: Path) -> None:
        stale = seed_vendor_copy(repo / "src" / "claude" / "skills", "local-skill")

        _written, removed, _skipped, _errors = generate_skills.prune_stale_claude_skill_support(
            repo, check=True
        )

        assert removed == 2
        assert (stale / "scripts" / "run.py").is_file()

    def test_sync_refuses_a_symlinked_stale_copy(self, repo: Path, tmp_path_factory) -> None:
        outside = tmp_path_factory.mktemp("outside")
        (outside / "keep.txt").write_text("x\n", encoding="utf-8")
        tree = repo / "src" / "claude" / "skills"
        tree.mkdir(parents=True, exist_ok=True)
        try:
            (tree / "local-skill").symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable")

        _written, _removed, _skipped, errors = generate_skills.prune_stale_claude_skill_support(
            repo
        )

        assert any("symlink" in err for err in errors)
        assert (outside / "keep.txt").is_file()

    def test_prune_ignores_names_that_are_not_given(self, tmp_path: Path) -> None:
        shipped = seed_vendor_copy(tmp_path, "shipped-skill")

        removed, errors = skill_support_mirror.prune_repo_local_vendor_copies(
            tmp_path, frozenset({"other"})
        )

        assert (removed, errors) == (0, [])
        assert shipped.is_dir()

    def test_copilot_mirror_removes_the_stale_copy(self, repo: Path) -> None:
        for name in ("local-skill", "shipped-skill"):
            (repo / ".claude" / "skills" / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        out = repo / "out" / "skills"
        stale = seed_vendor_copy(out, "local-skill")

        rc = generate_skills.generate_skills(minimal_platform_config(repo), repo)

        assert rc == 0
        assert not stale.exists()
        assert (out / "shipped-skill" / "helper.py").is_file()

    def test_copilot_validate_reports_the_stale_copy_as_drift(self, repo: Path) -> None:
        for name in ("local-skill", "shipped-skill"):
            (repo / ".claude" / "skills" / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        stale = seed_vendor_copy(repo / "out" / "skills", "local-skill")

        rc = generate_skills.generate_skills(minimal_platform_config(repo), repo, validate=True)

        assert rc == 1
        assert stale.is_dir()


class TestBinplace:
    """ADR-119: a ``link: true`` skills row links shipped skills, never repo-local ones."""

    @staticmethod
    def stale_plugin_copy(repo: Path) -> Path:
        stale = repo / "src" / "claude" / "skills" / "local-skill" / "SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("stale plugin copy\n", encoding="utf-8")
        return stale

    def setup_trees(self, repo: Path) -> None:
        platforms = repo / "templates" / "platforms"
        platforms.mkdir(parents=True, exist_ok=True)
        (platforms / "binplace.yaml").write_text(BINPLACE_MANIFEST, encoding="utf-8")
        skill_templates.compile_all(repo, validate=False)
        # The fixture's stand-in install directory for the shipped skill is
        # what binplace replaces with a link.
        shutil.rmtree(repo / ".claude" / "skills" / "shipped-skill")

    def test_check_reports_no_drift_for_a_repo_local_skill(self, repo: Path) -> None:
        self.setup_trees(repo)
        binplace_manifest.binplace(repo, check=False)

        result = binplace_manifest.binplace(repo, check=True)

        assert result.exit_code == 0
        assert result.drifted == []
        assert not any("local-skill" in path for path in result.unowned)

    def test_repo_local_skill_stays_a_real_directory(self, repo: Path) -> None:
        self.setup_trees(repo)

        binplace_manifest.binplace(repo, check=False)

        local = repo / ".claude" / "skills" / "local-skill"
        assert local.is_dir()
        assert not local.is_symlink()

    def test_leftover_plugin_copy_never_overwrites_the_install_file(self, repo: Path) -> None:
        self.setup_trees(repo)
        binplace_manifest.binplace(repo, check=False)
        self.stale_plugin_copy(repo)
        before = install_target(repo, "local-skill").read_bytes()

        check = binplace_manifest.binplace(repo, check=True)
        write = binplace_manifest.binplace(repo, check=False)

        assert check.drifted == []
        assert not any("local-skill" in path for path in write.written)
        assert install_target(repo, "local-skill").read_bytes() == before

    @needs_symlinks
    def test_shipped_skill_is_linked_to_the_plugin_tree(self, repo: Path) -> None:
        self.setup_trees(repo)

        result = binplace_manifest.binplace(repo, check=False)

        link = repo / ".claude" / "skills" / "shipped-skill"
        assert str(link) in result.written
        assert link.is_symlink()
        assert os.readlink(link) == "../../src/claude/skills/shipped-skill"
        assert install_target(repo, "shipped-skill").read_bytes() == (
            target(repo, "shipped-skill").read_bytes()
        )

    @needs_symlinks
    def test_check_still_reports_drift_for_a_shipped_skill(self, repo: Path) -> None:
        self.setup_trees(repo)
        binplace_manifest.binplace(repo, check=False)
        link = repo / ".claude" / "skills" / "shipped-skill"
        link.unlink()
        link.mkdir()
        (link / "SKILL.md").write_text("edited\n", encoding="utf-8")

        result = binplace_manifest.binplace(repo, check=True)

        assert result.exit_code == 2
        assert str(link) in result.drifted

    def test_allowlist_covers_the_repo_local_install_path(self, repo: Path) -> None:
        self.setup_trees(repo)

        allow = binplace_manifest.claude_allowlist(repo)

        assert install_target(repo, "local-skill") in allow
        assert target(repo, "local-skill") not in allow


class TestRealTree:
    """Assertions over the committed repository, not a fixture."""

    def flagged(self) -> frozenset[str]:
        return skill_distribution.repo_local_names(_REPO_ROOT)

    def test_some_skills_are_repo_local(self) -> None:
        assert self.flagged(), "no template carries distribution: repo-local"

    def test_no_repo_local_skill_exists_in_a_vendor_plugin_tree(self) -> None:
        leaked = [
            str(_REPO_ROOT / "src" / tree / "skills" / name)
            for name in self.flagged()
            for tree in ("claude", "copilot-cli")
            if (_REPO_ROOT / "src" / tree / "skills" / name).exists()
        ]

        assert leaked == []

    def test_every_repo_local_template_has_an_install_tree_skill(self) -> None:
        missing = [
            name
            for name in self.flagged()
            if not (_REPO_ROOT / ".claude" / "skills" / name / "SKILL.md").is_file()
        ]

        assert missing == []

    def test_external_claims_keeps_shipping(self) -> None:
        assert "ai-agents-external-claims" not in self.flagged()
        assert (_REPO_ROOT / "src/claude/skills/ai-agents-external-claims/SKILL.md").is_file()
