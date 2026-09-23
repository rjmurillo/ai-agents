#!/usr/bin/env python3
"""Tests for add/add evidence-conflict blocking in resolve_pr_conflicts.py.

Split from test_resolve_pr_conflicts.py to keep that file under the
file-size taste-lint ratchet (issue #2785 precedent); same import pattern.

CodeRabbit PRRT_kwDOQoWRls6ibh7v: accept-theirs alone silently discarded the
head branch's own record on an add/add conflict under an append-only
evidence directory (.project-toolkit/sessions/*, .project-toolkit/qa/*,
.project-toolkit/retrospective/*; PR #4856). These tests prove the fix: such a
conflict is now reported "blocked" instead of auto-resolved, while an
ordinary modify/modify conflict on the same path pattern still auto-resolves.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")
_is_evidence_pattern = mod._is_evidence_pattern
_is_add_add_conflict = mod._is_add_add_conflict
_resolve_conflicted_file = mod._resolve_conflicted_file


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )


class TestIsEvidencePattern:
    """Detection of append-only evidence directories (PR #4856)."""

    def test_session_qa_retrospective_match(self) -> None:
        assert _is_evidence_pattern(".project-toolkit/sessions/2026-01-01.json")
        assert _is_evidence_pattern(".project-toolkit/qa/2026-01-01-report.md")
        assert _is_evidence_pattern(".project-toolkit/retrospective/2026-01-01-notes.md")

    def test_other_agents_paths_do_not_match(self) -> None:
        assert not _is_evidence_pattern(".agents/governance/PROJECT-CONSTRAINTS.md")
        assert not _is_evidence_pattern("src/main.py")


class TestIsAddAddConflict:
    """Stage-1 (common ancestor) absence detects an add/add conflict."""

    def _make_add_add(self, repo: Path, rel: str, ours: str, theirs: str) -> None:
        """Two branches independently create *rel* with no shared ancestor."""
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")
        _git(repo, "config", "commit.gpgsign", "false")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "base")
        _git(repo, "checkout", "-b", "pr")
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ours, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "ours adds file")
        _git(repo, "checkout", "main")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(theirs, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "theirs adds same-named file")
        _git(repo, "checkout", "pr")
        merge = _git(repo, "merge", "main")
        assert merge.returncode != 0, "expected an add/add conflict"

    def _make_modify_modify(self, repo: Path, rel: str) -> None:
        """Both branches modify a file that has a common ancestor."""
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")
        _git(repo, "config", "commit.gpgsign", "false")
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("base\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "base adds file")
        _git(repo, "checkout", "-b", "pr")
        path.write_text("ours\n", encoding="utf-8")
        _git(repo, "commit", "-am", "ours modifies")
        _git(repo, "checkout", "main")
        path.write_text("theirs\n", encoding="utf-8")
        _git(repo, "commit", "-am", "theirs modifies")
        _git(repo, "checkout", "pr")
        merge = _git(repo, "merge", "main")
        assert merge.returncode != 0, "expected a modify/modify conflict"

    def test_add_add_has_no_stage_1(self, tmp_path: Path) -> None:
        rel = ".project-toolkit/sessions/2026-01-01.json"
        self._make_add_add(tmp_path, rel, '{"ours": true}\n', '{"theirs": true}\n')
        assert _is_add_add_conflict(rel, cwd=str(tmp_path)) is True

    def test_modify_modify_has_stage_1(self, tmp_path: Path) -> None:
        rel = ".project-toolkit/sessions/2026-01-01.json"
        self._make_modify_modify(tmp_path, rel)
        assert _is_add_add_conflict(rel, cwd=str(tmp_path)) is False

    def test_no_conflict_returns_false(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-b", "main")
        assert _is_add_add_conflict(".project-toolkit/sessions/missing.json", cwd=str(tmp_path)) is False

    def test_inspection_failure_returns_none(self, tmp_path: Path) -> None:
        """CodeRabbit PRRT_kwDOQoWRls6icJzj: fail closed, not "not add/add".

        *tmp_path* is not a git repository, so ``git ls-files -u`` exits
        nonzero. The old code returned False here, which let the evidence
        conflict fall through to accept-theirs.
        """
        assert _is_add_add_conflict(".project-toolkit/sessions/x.json", cwd=str(tmp_path)) is None


class TestResolveConflictedFileEvidenceAddAdd:
    """_resolve_conflicted_file blocks add/add evidence conflicts (PR #4856)."""

    def test_add_add_evidence_conflict_blocks(self, tmp_path: Path) -> None:
        rel = ".project-toolkit/sessions/2026-01-01.json"
        helper = TestIsAddAddConflict()
        helper._make_add_add(tmp_path, rel, '{"ours": true}\n', '{"theirs": true}\n')
        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "files_resolved": [],
            "files_blocked": [],
        }
        status = _resolve_conflicted_file(rel, result, cwd=str(tmp_path))
        assert status == "blocked"
        assert result["files_blocked"] == [rel]
        assert result["files_resolved"] == []
        # The head branch's own record must survive untouched, not be
        # silently discarded by an accept-theirs checkout.
        assert '"ours": true' in (tmp_path / rel).read_text(encoding="utf-8")

    def test_modify_modify_evidence_conflict_still_auto_resolves(self, tmp_path: Path) -> None:
        rel = ".project-toolkit/sessions/2026-01-01.json"
        helper = TestIsAddAddConflict()
        helper._make_modify_modify(tmp_path, rel)
        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "files_resolved": [],
            "files_blocked": [],
        }
        status = _resolve_conflicted_file(rel, result, cwd=str(tmp_path))
        assert status == "resolved"
        assert result["files_resolved"] == [rel]

    def test_ls_files_failure_blocks_instead_of_accept_theirs(self, tmp_path: Path) -> None:
        """CodeRabbit PRRT_kwDOQoWRls6icJzj: fail closed on inspection failure.

        *tmp_path* is not a git repository, so ``git ls-files -u`` fails.
        Before the fix, that failure made ``_is_add_add_conflict`` return
        False, which let this evidence path fall through to
        ``is_auto_resolvable`` and accept-theirs, discarding the evidence
        record without ever inspecting it.
        """
        rel = ".project-toolkit/sessions/2026-01-01.json"
        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "files_resolved": [],
            "files_blocked": [],
        }
        status = _resolve_conflicted_file(rel, result, cwd=str(tmp_path))
        assert status == "blocked"
        assert result["files_blocked"] == [rel]
        assert result["files_resolved"] == []
