#!/usr/bin/env python3
"""Tests for conflicted-file dispatch and plugin manifest path containment in resolve_pr_conflicts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
TESTS_MERGE_RESOLVER_DIR = str(Path(__file__).resolve().parent)
if TESTS_MERGE_RESOLVER_DIR not in sys.path:
    sys.path.insert(0, TESTS_MERGE_RESOLVER_DIR)

from claude_skills_import import import_skill_script
from manifest_conflict_fixtures import manifest_json

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")

resolve_plugin_manifest_conflict = mod.resolve_plugin_manifest_conflict
_resolve_conflicted_file = mod._resolve_conflicted_file

class TestResolveConflictedFileDispatch:
    """_resolve_conflicted_file routes manifests, patterns, and failures."""

    def _result(self) -> dict[str, Any]:
        return {"success": False, "message": "", "files_resolved": [], "files_blocked": []}

    def test_plugin_manifest_resolved(self) -> None:
        result = self._result()
        with patch.object(mod, "resolve_plugin_manifest_conflict", return_value=True):
            status = _resolve_conflicted_file(".claude/.claude-plugin/plugin.json", result)
        assert status == "resolved"
        assert result["files_resolved"] == [".claude/.claude-plugin/plugin.json"]

    def test_plugin_manifest_unresolvable_blocks(self) -> None:
        result = self._result()
        with patch.object(mod, "resolve_plugin_manifest_conflict", return_value=False):
            status = _resolve_conflicted_file(".claude/.claude-plugin/plugin.json", result)
        assert status == "blocked"
        assert result["files_blocked"] == [".claude/.claude-plugin/plugin.json"]

    def test_auto_resolvable_takes_theirs(self) -> None:
        result = self._result()
        ok = MagicMock(returncode=0)
        with patch.object(mod, "_run_git", return_value=ok) as run_git:
            status = _resolve_conflicted_file(".agents/governance/PROJECT-CONSTRAINTS.md", result)
        assert status == "resolved"
        assert result["files_resolved"] == [".agents/governance/PROJECT-CONSTRAINTS.md"]
        assert run_git.call_args_list[0].args[:2] == ("checkout", "--theirs")

    def test_unknown_file_blocks(self) -> None:
        result = self._result()
        status = _resolve_conflicted_file("src/main.py", result)
        assert status == "blocked"
        assert result["files_blocked"] == ["src/main.py"]

    def test_checkout_failure_is_error(self) -> None:
        result = self._result()
        fail = MagicMock(returncode=1)
        with patch.object(mod, "_run_git", return_value=fail):
            status = _resolve_conflicted_file(".agents/governance/PROJECT-CONSTRAINTS.md", result)
        assert status == "error"
        assert "checkout --theirs" in result["message"]


class TestResolvePluginManifestPathContainment:
    """The manifest write refuses paths that escape the conflict repo (CWE-22)."""

    def test_path_escaping_cwd_is_blocked(self, tmp_path: Path) -> None:
        ours = MagicMock(returncode=0, stdout=manifest_json("0.5.2"))
        theirs = MagicMock(returncode=0, stdout=manifest_json("0.5.3"))
        with patch.object(mod, "_run_git", side_effect=[ours, theirs]):
            resolved = resolve_plugin_manifest_conflict(
                "../escape-2543/.claude-plugin/plugin.json",
                cwd=str(tmp_path),
            )
        assert resolved is False
        # tmp_path.parent is the shared pytest session dir; assert on the
        # unique escape target, not a generic name another test may create.
        escape = tmp_path.parent / "escape-2543" / ".claude-plugin" / "plugin.json"
        assert not escape.exists()
