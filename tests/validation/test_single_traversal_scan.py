"""Tests for single-traversal scan_all (issue #4211, TOCTOU).

The coverage decision and the baseline contents must come from the same
snapshot. These tests verify that scan_all() returns all four values from
one traversal, so a tree mutation between walks cannot produce a short
baseline that passes the coverage check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validation.check_skill_md_portability as cmp


def _make_skill(root: Path, name: str, content: str = "clean\n") -> Path:
    skill = root / ".claude" / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    md = skill / "SKILL.md"
    md.write_text(content, encoding="utf-8")
    (root / "src" / "copilot-cli" / "skills").mkdir(parents=True, exist_ok=True)
    (root / "src" / "copilot-cli" / "instructions").mkdir(parents=True, exist_ok=True)
    return md


class TestScanAllReturnsSingleSnapshot:
    """scan_all returns ref counts, marker counts, coverage, and drift data from one walk."""

    def test_returns_four_values(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _make_skill(repo, "clean")
        result = cmp.scan_all(repo)
        assert len(result) == 4
        ref_counts, marker_counts, scanned_by_root, drift_failures = result
        assert isinstance(ref_counts, dict)
        assert isinstance(marker_counts, dict)
        assert isinstance(scanned_by_root, dict)
        assert isinstance(drift_failures, list)

    def test_ref_counts_match_scan_plugin_roots(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _make_skill(repo, "with_ref", "See .agents/lib/helper.py\n")

        ref_counts, _, _, _ = cmp.scan_all(repo)
        standalone = cmp.scan_plugin_roots(repo)

        assert ref_counts == standalone

    def test_scanned_by_root_matches_scanned_markdown_by_root(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        _make_skill(repo, "a")
        _make_skill(repo, "b")

        _, _, scanned, _ = cmp.scan_all(repo)
        standalone = cmp.scanned_markdown_by_root(repo)

        assert scanned == standalone

    def test_marker_counts_match_scan_marker_suppressions(
        self, tmp_path: Path
    ) -> None:
        content = "<!-- vendor-portability: deliberate -->\nSee .agents/x\n"
        repo = tmp_path / "repo"
        _make_skill(repo, "marked", content)

        _, marker_counts, _, _ = cmp.scan_all(repo)
        standalone = cmp.scan_marker_suppressions(repo)

        assert marker_counts == standalone

    def test_empty_tree_gives_zero_scanned(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)

        _, _, scanned, _ = cmp.scan_all(repo)

        assert ".claude/skills" in scanned
        assert scanned[".claude/skills"] == 0

    def test_extra_dirs_contribute_to_both_ref_counts_and_coverage(
        self, tmp_path: Path
    ) -> None:
        """Issue #5214 review: an extra dir must be visible in files_by_root too.

        Previously extra dirs fed ref_counts but were absent from
        files_by_root, so a root that went unread (renamed, deleted, or a
        broken generator run) looked identical to a root that was read and
        found clean. Both must now be observable from one scan_all() call.
        """
        repo = tmp_path / "repo"
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        commands = repo / ".claude" / "commands"
        commands.mkdir(parents=True)
        (commands / "spec.md").write_text("See .agents/lib/x\n", encoding="utf-8")

        ref_counts, _, scanned, _ = cmp.scan_all(repo)

        assert ".claude/commands/spec.md" in ref_counts
        assert scanned.get(".claude/commands") == 1

    def test_extra_dirs_contribute_to_marker_counts_and_coverage(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        commands = repo / ".claude" / "commands"
        commands.mkdir(parents=True)
        (commands / "spec.md").write_text(
            "<!-- vendor-portability: declared -->\nSee .agents/lib/x\n",
            encoding="utf-8",
        )

        _, marker_counts, scanned, _ = cmp.scan_all(repo)

        assert marker_counts == {".claude/commands/spec.md": 1}
        assert scanned.get(".claude/commands") == 1


class TestScanAllUsedByMain:
    """main() calls scan_all and uses the single-snapshot result."""

    def test_scan_all_called_once_per_main_invocation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Replacing scan_all with a counter proves main calls it exactly once."""
        repo = tmp_path / "repo"
        _make_skill(repo, "a")
        # Baseline must be inside the repo to pass the path check
        baseline_dir = repo / "scripts" / "validation"
        baseline_dir.mkdir(parents=True)
        baseline = baseline_dir / "b.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")

        call_count = 0
        real_scan_all = cmp.scan_all

        def counting_scan_all(root: Path, *, check_drift: bool = False) -> object:
            nonlocal call_count
            call_count += 1
            return real_scan_all(root, check_drift=check_drift)

        monkeypatch.setattr(cmp, "scan_all", counting_scan_all)
        cmp.main(["--repo-root", str(repo), "--baseline", str(baseline)])

        assert call_count == 1, f"scan_all was called {call_count} times, expected 1"
