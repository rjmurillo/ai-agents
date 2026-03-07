"""Tests for improve_memory_graph_density.py."""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import improve_memory_graph_density


class TestDomainPatterns:
    """Tests for DOMAIN_PATTERNS ordering."""

    def test_specific_before_general(self):
        patterns = list(improve_memory_graph_density.DOMAIN_PATTERNS.keys())
        git_hooks_idx = patterns.index("git-hooks-")
        git_idx = patterns.index("git-")
        assert git_hooks_idx < git_idx

    def test_pr_comment_before_pr(self):
        patterns = list(improve_memory_graph_density.DOMAIN_PATTERNS.keys())
        pr_comment_idx = patterns.index("pr-comment-")
        pr_idx = patterns.index("pr-")
        assert pr_comment_idx < pr_idx


class TestFindRelatedFiles:
    """Tests for _find_related_files function."""

    def test_finds_same_domain(self, tmp_path):
        (tmp_path / "security-scan.md").write_text("# Scan")
        (tmp_path / "security-audit.md").write_text("# Audit")
        (tmp_path / "other-file.md").write_text("# Other")
        all_files = sorted(tmp_path.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}

        related = improve_memory_graph_density._find_related_files(
            "security-scan", all_files, names
        )
        assert "security-audit" in related
        assert "other-file" not in related

    def test_includes_index_file(self, tmp_path):
        (tmp_path / "security-scan.md").write_text("# Scan")
        (tmp_path / "securitys-index.md").write_text("| key | val |")
        all_files = sorted(tmp_path.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}

        related = improve_memory_graph_density._find_related_files(
            "security-scan", all_files, names
        )
        assert "securitys-index" in related

    def test_limits_to_five(self, tmp_path):
        for i in range(10):
            (tmp_path / f"git-topic-{i}.md").write_text(f"# Topic {i}")
        all_files = sorted(tmp_path.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}

        related = improve_memory_graph_density._find_related_files(
            "git-topic-0", all_files, names
        )
        assert len(related) <= 5

    def test_no_matches(self, tmp_path):
        (tmp_path / "unique-standalone.md").write_text("# Standalone")
        all_files = sorted(tmp_path.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}

        related = improve_memory_graph_density._find_related_files(
            "unique-standalone", all_files, names
        )
        assert len(related) == 0


class TestProcessFiles:
    """Integration tests for process_files function."""

    def test_skips_index_files(self, tmp_path):
        (tmp_path / "test-index.md").write_text("| key | val |")
        # process_files signature: (memories_path, files, dry_run, output_json)
        stats = improve_memory_graph_density.process_files(
            tmp_path, None, False, True
        )
        assert stats["FilesModified"] == 0

    def test_adds_related_section(self, tmp_path):
        (tmp_path / "git-hooks.md").write_text("# Git Hooks")
        (tmp_path / "git-config.md").write_text("# Git Config")

        stats = improve_memory_graph_density.process_files(
            tmp_path, None, False, False
        )
        assert stats["FilesModified"] >= 1

        content = (tmp_path / "git-hooks.md").read_text()
        assert "## Related" in content

    def test_dry_run_no_write(self, tmp_path):
        (tmp_path / "git-hooks.md").write_text("# Git Hooks")
        (tmp_path / "git-config.md").write_text("# Git Config")

        stats = improve_memory_graph_density.process_files(
            tmp_path, None, True, False
        )
        assert stats["FilesModified"] >= 1

        content = (tmp_path / "git-hooks.md").read_text()
        assert "## Related" not in content

    def test_skips_existing_related(self, tmp_path):
        (tmp_path / "git-hooks.md").write_text("# Git Hooks\n\n## Related\n\n- existing")
        (tmp_path / "git-config.md").write_text("# Git Config")

        stats = improve_memory_graph_density.process_files(
            tmp_path, None, False, False
        )
        assert stats["FilesModified"] == 0 or "git-hooks.md" not in str(stats)
