"""Tests for symlink scan root validation (issue #4212, CWE-22).

A scan root symlinked outside the repository is a path-traversal risk.
Both portability ratchets must refuse it. These tests create real symlinks
pointing outside a temporary repo root and assert the scan refuses them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validation.check_skill_md_exec_portability as exec_cmp
import scripts.validation.check_skill_md_portability as cmp
from scripts.validation import portability_common as common


def _make_repo(tmp_path: Path) -> Path:
    """Return a minimal repository layout under tmp_path/repo."""
    repo = tmp_path / "repo"
    skills = repo / ".claude" / "skills"
    skills.mkdir(parents=True)
    (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)
    return repo


class TestRefuseSymlinkedScanRoot:
    """portability_common.refuse_symlinked_scan_root boundary tests."""

    def test_rejects_scan_root_symlinked_outside_repo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        link = repo / "external_skills"
        link.symlink_to(outside)

        refused = common.refuse_symlinked_scan_root(repo, link)

        assert refused is True
        err = capsys.readouterr().err
        assert "CWE-22" in err or "outside" in err

    def test_allows_real_dir_inside_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        real_dir = repo / ".claude" / "skills"
        real_dir.mkdir(parents=True)

        refused = common.refuse_symlinked_scan_root(repo, real_dir)

        assert refused is False

    def test_rejects_symlink_pointing_to_sibling_inside_repo_via_outside(
        self, tmp_path: Path
    ) -> None:
        """A symlink that resolves outside even if its target looks nearby."""
        outside = tmp_path / "outside"
        outside.mkdir()
        repo = tmp_path / "repo"
        (repo / ".claude" / "skills").mkdir(parents=True)
        link = repo / ".claude" / "link_to_outside"
        link.symlink_to(outside)

        refused = common.refuse_symlinked_scan_root(repo, link)

        assert refused is True

    def test_rejects_symlink_inside_repo_pointing_outside(
        self, tmp_path: Path
    ) -> None:
        """Even a symlink inside the repo tree is refused when it points outside."""
        outside = tmp_path / "outside_dir"
        outside.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        link = repo / "escape"
        link.symlink_to(outside)

        refused = common.refuse_symlinked_scan_root(repo, link)

        assert refused is True


class TestMdPortabilityScanAllRejectsSymlinkedRoot:
    """scan_all in check_skill_md_portability refuses symlinked scan roots."""

    def test_symlinked_plugin_root_raises(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        (outside / "skills" / "a").mkdir(parents=True)
        (outside / "skills" / "a" / "SKILL.md").write_text("", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        # Create symlink: repo/.claude -> outside
        (repo / ".claude").symlink_to(outside)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)

        with pytest.raises(OSError, match="outside the repository root"):
            cmp.scan_all(repo)

    def test_real_plugin_root_is_scanned(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        skill = repo / ".claude" / "skills" / "a"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "No references here.\n", encoding="utf-8"
        )

        ref_counts, marker_counts, scanned, drift_failures = cmp.scan_all(repo)

        assert ".claude/skills" in scanned
        assert scanned[".claude/skills"] == 1
        assert drift_failures == []

    def test_symlinked_extra_dir_raises(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside_commands"
        outside.mkdir()
        repo = tmp_path / "repo"
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        # commands dir is symlinked outside
        (repo / ".claude" / "commands").symlink_to(outside)

        with pytest.raises(OSError, match="outside the repository root"):
            cmp.scan_all(repo)


class TestExecPortabilityScanAllRejectsSymlinkedRoot:
    """scan_all in check_skill_md_exec_portability refuses symlinked scan roots."""

    def test_symlinked_scan_root_raises(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        (outside / "skill_a").mkdir(parents=True)
        (outside / "skill_a" / "SKILL.md").write_text("", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".claude").mkdir()
        # Link .claude/skills -> outside dir that has skill dirs
        (repo / ".claude" / "skills").symlink_to(outside)

        with pytest.raises(OSError, match="outside the repository root"):
            exec_cmp.scan_all(repo)

    def test_real_scan_root_scans_normally(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        skill = repo / ".claude" / "skills" / "a"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("clean file\n", encoding="utf-8")

        exec_counts, marker_counts, by_root = exec_cmp.scan_all(repo)

        assert ".claude/skills" in by_root
        assert by_root[".claude/skills"] == 1
        assert exec_counts == {}


class TestMdPortabilityMainRejectsSymlinkedRoot:
    """main() in check_skill_md_portability exits 2 when a scan root is symlinked outside."""

    def test_main_exits_2_on_symlinked_scan_root(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside = tmp_path / "outside"
        (outside / "skills" / "a").mkdir(parents=True)
        (outside / "skills" / "a" / "SKILL.md").write_text("", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".claude").symlink_to(outside)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (repo / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "b.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")

        rc = cmp.main(["--repo-root", str(repo), "--baseline", str(baseline)])

        assert rc == 2
        err = capsys.readouterr().err
        assert "outside the repository root" in err or "CWE-22" in err
