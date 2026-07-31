"""Tests for scan_principles_core -- the types and utilities extracted from
scan_principles.py (issue #4028).

The checkers and CLI remain in scan_principles.py; this file verifies that
the core module's public interface is intact and that the functions that were
moved still behave identically to their originals.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to sys.path so sibling import works when running
# pytest directly from the project root.
_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[3]
    / ".claude/skills/golden-principles/scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import scan_principles_core as core


class TestPublicInterface:
    """Core module exposes the expected symbols."""

    def test_exit_constants(self) -> None:
        assert core.EXIT_SUCCESS == 0
        assert core.EXIT_ERROR == 1
        assert core.EXIT_VIOLATIONS == 10

    def test_all_rules_tuple(self) -> None:
        assert "script-language" in core.ALL_RULES
        assert "skill-frontmatter" in core.ALL_RULES
        assert "agent-definition" in core.ALL_RULES
        assert "yaml-logic" in core.ALL_RULES
        assert "actions-pinned" in core.ALL_RULES

    def test_violation_dataclass(self) -> None:
        v = core.Violation(
            rule="script-language",
            principle="GP-001",
            severity="error",
            file="x.sh",
            line=1,
            message="msg",
            remediation="fix",
        )
        assert v.rule == "script-language"
        assert v.severity == "error"

    def test_scan_result_properties(self) -> None:
        result = core.ScanResult()
        result.violations = [
            core.Violation("r", "p", "error", "f", 1, "m", "fix"),
            core.Violation("r", "p", "warning", "f", 2, "m", "fix"),
        ]
        assert result.error_count == 1
        assert result.warning_count == 1


class TestIsSafePath:
    def test_relative_safe(self) -> None:
        assert core.is_safe_path("some/path/file.py") is True

    def test_absolute_safe(self) -> None:
        assert core.is_safe_path("/abs/path/file.py") is True

    def test_traversal_rejected(self) -> None:
        assert core.is_safe_path("../../etc/passwd") is False


class TestHasSuppression:
    def test_detects_suppression(self) -> None:
        lines = ["# golden-principle: ignore script-language\n", "echo hi\n"]
        assert core.has_suppression(lines, "script-language") is True

    def test_returns_false_for_different_rule(self) -> None:
        lines = ["# golden-principle: ignore yaml-logic\n"]
        assert core.has_suppression(lines, "script-language") is False

    def test_only_checks_first_10_lines(self) -> None:
        lines = ["normal\n"] * 10 + ["# golden-principle: ignore script-language\n"]
        assert core.has_suppression(lines, "script-language") is False


class TestGetRepoFiles:
    def test_collects_visible_files(self, tmp_path: Path) -> None:
        (tmp_path / "file.py").write_text("x", encoding="utf-8")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "other.py").write_text("y", encoding="utf-8")
        files = core.get_repo_files(str(tmp_path))
        names = [Path(f).name for f in files]
        assert "file.py" in names
        assert "other.py" in names

    def test_skips_hidden_dirs_except_claude_agents_github(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("s", encoding="utf-8")
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "skill.py").write_text("c", encoding="utf-8")
        files = core.get_repo_files(str(tmp_path))
        paths = [Path(f).parts for f in files]
        assert not any(".hidden" in p for p in paths)
        assert any(".claude" in p for p in paths)


class TestReadFileLines:
    def test_reads_utf8(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("hello\nworld\n", encoding="utf-8")
        assert core.read_file_lines(str(f)) == ["hello\n", "world\n"]

    def test_returns_empty_for_missing_file(self) -> None:
        assert core.read_file_lines("/nonexistent/path/file.py") == []
