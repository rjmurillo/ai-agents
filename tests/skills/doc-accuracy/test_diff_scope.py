#!/usr/bin/env python3
"""Tests for line-scoped gating in doc_accuracy --diff-base mode.

Owner decision: with --diff-base, only claims whose source lines overlap the
PR's changed hunks may block. Claims in untouched lines of a changed doc are
reported as ``info``. All tests use real git repositories.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_diff_scope",
)

FENCE = "```"
SOURCE = "class Real:\n    pass\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
    )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "src.py").write_text(SOURCE)
    for name, text in files.items():
        (repo / name).write_text(text)
    _commit(repo, "base")
    return repo


def _example(symbol: str) -> str:
    """A python example whose only CamelCase symbol is ``symbol``."""
    return f"{FENCE}python\nx = {symbol}()\n{FENCE}\n"


def _run_gate(repo: Path, tmp_path: Path, *extra: str) -> tuple[int, dict]:
    out = tmp_path / "out"
    code = mod.main(
        ["--target", str(repo), "--output-dir", str(out), "--format", "gate",
         *extra]
    )
    return code, json.loads((out / "compilability-findings.json").read_text())


def _gate(out_dir: Path) -> dict:
    return json.loads((out_dir / "gate-result.json").read_text())


class TestDiffScopedGate:
    def test_untouched_illustrative_block_does_not_block(
        self, tmp_path: Path
    ) -> None:
        body = "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n" + _example("Ghost")
        repo = _make_repo(tmp_path, {"doc.md": body})
        (repo / "doc.md").write_text(body.replace("| 1 | 2 |", "| 3 | 4 |"))
        _commit(repo, "edit row")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 0
        assert _gate(tmp_path / "out")["verdict"] == "PASS"
        assert _gate(tmp_path / "out")["blocking_findings"] == 0
        finding = data["findings"][0]
        assert finding["severity"] == "info"
        assert finding["original_severity"] == "high"
        assert finding["in_diff"] is False

    def test_finding_inside_changed_hunk_still_blocks(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, {"doc.md": "# T\n\n" + _example("Real")})
        (repo / "doc.md").write_text("# T\n\n" + _example("Ghost"))
        _commit(repo, "break example")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 10
        finding = data["findings"][0]
        assert finding["severity"] == "high"
        assert finding["in_diff"] is True
        assert "original_severity" not in finding

    def test_mixed_blocks_only_touched_one_blocks(self, tmp_path: Path) -> None:
        old = "# T\n\n" + _example("Alpha") + "\ntext\n\n" + _example("Beta")
        repo = _make_repo(tmp_path, {"doc.md": old})
        (repo / "doc.md").write_text(old.replace("Beta", "Gamma"))
        _commit(repo, "edit second")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        by_symbol = {f["evidence"]["symbol"]: f for f in data["findings"]}
        assert code == 10
        assert by_symbol["Gamma"]["in_diff"] is True
        assert by_symbol["Alpha"]["severity"] == "info"
        assert _gate(tmp_path / "out")["blocking_findings"] == 1

    def test_new_file_is_in_scope_on_every_line(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {})
        (repo / "new.md").write_text("# New\n\n" + _example("Ghost"))
        _commit(repo, "add doc")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 10
        assert data["findings"][0]["in_diff"] is True

    def test_pure_rename_keeps_old_findings_out_of_scope(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, {"old.md": "# T\n\n" + _example("Ghost")})
        _git(repo, "mv", "old.md", "moved.md")
        _commit(repo, "rename")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 0
        assert data["findings"][0]["file"] == "moved.md"
        assert data["findings"][0]["in_diff"] is False

    def test_rename_with_edit_scopes_to_edited_hunk(
        self, tmp_path: Path
    ) -> None:
        text = "# T\n\n" + _example("Alpha") + "\ntext\n\n" + _example("Beta")
        repo = _make_repo(tmp_path, {"old.md": text})
        _git(repo, "mv", "old.md", "moved.md")
        (repo / "moved.md").write_text(text.replace("Beta", "Gamma"))
        _commit(repo, "rename and edit")

        _, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        by_symbol = {f["evidence"]["symbol"]: f for f in data["findings"]}
        assert by_symbol["Gamma"]["in_diff"] is True
        assert by_symbol["Alpha"]["in_diff"] is False

    def test_multiple_hunks_each_scope_their_own_block(
        self, tmp_path: Path
    ) -> None:
        pad = "\n".join(f"filler {n}" for n in range(6)) + "\n"
        old = ("# T\n\n" + _example("One") + pad + _example("Two") + pad
               + _example("Three"))
        repo = _make_repo(tmp_path, {"doc.md": old})
        new = old.replace("One", "Uno").replace("Three", "Tres")
        (repo / "doc.md").write_text(new)
        _commit(repo, "edit first and last")

        _, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        in_diff = {f["evidence"]["symbol"]: f["in_diff"] for f in data["findings"]}
        assert in_diff == {"Uno": True, "Two": False, "Tres": True}

    def test_claim_spanning_hunk_boundary_is_in_scope(
        self, tmp_path: Path
    ) -> None:
        old = f"# T\n\n{FENCE}python\nx = Ghost()\ny = 1\nz = 2\n{FENCE}\n"
        repo = _make_repo(tmp_path, {"doc.md": old})
        (repo / "doc.md").write_text(old.replace("z = 2", "z = 3"))
        _commit(repo, "edit last line of block")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 10
        assert data["findings"][0]["in_diff"] is True

    def test_pure_deletion_inside_block_is_in_scope(self, tmp_path: Path) -> None:
        old = f"# T\n\n{FENCE}python\nx = Ghost()\ny = 1\nz = 2\n{FENCE}\n"
        repo = _make_repo(tmp_path, {"doc.md": old})
        (repo / "doc.md").write_text(old.replace("y = 1\n", ""))
        _commit(repo, "delete a line in block")

        _, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert data["findings"][0]["in_diff"] is True

    def test_edit_after_block_does_not_touch_block(self, tmp_path: Path) -> None:
        old = "# T\n\n" + _example("Ghost") + "\ntail one\n"
        repo = _make_repo(tmp_path, {"doc.md": old})
        (repo / "doc.md").write_text(old.replace("tail one", "tail two"))
        _commit(repo, "edit tail")

        code, data = _run_gate(repo, tmp_path, "--diff-base", "HEAD~1")

        assert code == 0
        assert data["findings"][0]["in_diff"] is False


class TestFullFileBehaviorUnchanged:
    def test_without_diff_base_untouched_block_still_blocks(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, {"doc.md": "# T\n\n" + _example("Ghost")})

        code, data = _run_gate(repo, tmp_path)

        assert code == 10
        finding = data["findings"][0]
        assert finding["severity"] == "high"
        assert "in_diff" not in finding
        assert "original_severity" not in finding

    def test_assessment_has_no_changed_lines_without_diff_base(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, {"doc.md": "# T\n"})

        assert mod.run_assessment(repo)["changed_lines"] is None

    def test_check_gate_never_blocks_on_info(self) -> None:
        data = {"status": "COMPLETED", "findings": [
            {"severity": "info"},
        ]}

        for threshold in ("critical", "high", "medium", "low"):
            result = mod.check_gate(data, threshold)
            assert result["verdict"] == "PASS"
            assert result["by_severity"] == {"info": 1}


class TestHunkParsing:
    def test_single_line_hunk_without_count(self) -> None:
        patch = "+++ b/a.md\n@@ -3 +3 @@\n-x\n+y\n"
        assert mod._parse_unified_zero(patch) == {"a.md": [[3, 3]]}

    def test_zero_count_hunk_marks_neighbors(self) -> None:
        patch = "+++ b/a.md\n@@ -4,2 +3,0 @@\n"
        assert mod._parse_unified_zero(patch) == {"a.md": [[3, 4]]}

    def test_pure_rename_is_recorded_with_no_ranges(self) -> None:
        patch = (
            "diff --git a/o.md b/n.md\nsimilarity index 100%\n"
            "rename from o.md\nrename to n.md\n"
        )
        assert mod._parse_unified_zero(patch) == {"n.md": []}

    def test_deleted_file_is_not_recorded(self) -> None:
        patch = "--- a/a.md\n+++ /dev/null\n@@ -1,2 +0,0 @@\n"
        assert mod._parse_unified_zero(patch) == {}

    def test_quoted_path_is_decoded(self) -> None:
        patch = '+++ "b/caf\\303\\251 \\"q\\".md"\n@@ -1 +1 @@\n'
        assert mod._parse_unified_zero(patch) == {'café "q".md': [[1, 1]]}

    def test_file_without_hunks_gets_whole_file_range(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, {"doc.md": "# T\n\n" + _example("Ghost")})
        _git(repo, "update-index", "--chmod=+x", "doc.md")
        _git(repo, "commit", "-q", "-m", "mode only")

        result = mod.run_assessment(repo, diff_base="HEAD~1")

        assert result["changed_lines"]["doc.md"] == [[1, 6]]

    def test_claim_overlap_edges(self) -> None:
        claim = {"line": 10, "end_line": 12, "type": "code_example"}
        assert mod._claim_in_ranges(claim, [[12, 12]])
        assert mod._claim_in_ranges(claim, [[8, 10]])
        assert not mod._claim_in_ranges(claim, [[13, 20]])
        assert not mod._claim_in_ranges(claim, [])
