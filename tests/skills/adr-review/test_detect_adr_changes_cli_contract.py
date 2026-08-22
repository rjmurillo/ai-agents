#!/usr/bin/env python3
"""CLI/module-shape contract for detect_adr_changes: constants, argparse, and
main()'s multi-directory scan.

Split from ``test_detect_adr_changes.py`` rather than appended to it. These
six cases were ported from the stale, colocated
``.claude/skills/adr-review/tests/test_detect_adr_changes.py`` (removed:
PR #5209 round-4 review; that copy predated the ``tests/skills/`` relocation
and violated ``.claude/rules/testing.md`` MUST 6 / ``.claude/rules/claude-agents.md``
MUST 3, tests must live under repo ``tests/``, never a shipped skill
directory). Appending them to the main module pushed it from 494 to 601
lines, over the 500-line ceiling the taste-lint file-size rule enforces. A
suppression would have been the cheaper move and the wrong one: these cases
share a single premise, that the module's declared shape (its location
constants, its CLI surface, and every directory ``main()`` promises to scan)
is itself a contract worth pinning independent of any one behavior, so they
form a cohesive module on their own terms. Same split, same reasoning, as
``test_detect_adr_changes_encoding.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")

main = mod.main
build_parser = mod.build_parser


def test_declared_adr_locations_are_monitored() -> None:
    """`ADR_PATTERNS`/`ADR_DIRECTORIES` name every location `main()` scans.

    Pinned so a location added to one tuple but not the other silently
    narrows either the change-detection glob or the dependent-ADR search
    without any test noticing.
    """
    assert mod.ADR_PATTERNS == (
        ".agents/architecture/ADR-*.md",
        "docs/adr/ADR-*.md",
        "docs/architecture/ADR-*.md",
        "docs/decisions/ADR-*.md",
        "architecture/decisions/ADR-*.md",
    )
    assert mod.ADR_DIRECTORIES == (
        ".agents/architecture",
        "docs/adr",
        "docs/architecture",
        "docs/decisions",
        "architecture/decisions",
    )


class TestBuildParser:
    """Tests for build_parser()."""

    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.base_path == "."
        assert args.since_commit == "HEAD~1"
        assert args.include_untracked is False

    def test_custom_args(self) -> None:
        args = build_parser().parse_args(
            [
                "--base-path",
                "/tmp/repo",
                "--since-commit",
                "abc123",
                "--include-untracked",
            ]
        )
        assert args.base_path == "/tmp/repo"
        assert args.since_commit == "abc123"
        assert args.include_untracked is True

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0


class TestMainScansEveryDeclaredLocation:
    """`main()` must honor every entry in `ADR_DIRECTORIES`, not just the primary
    one, and must see an untracked file when asked to.

    A private `git_repo` fixture, not the one in
    `test_detect_adr_changes.py::TestMain`: splitting the file means splitting
    the fixture too, and a two-commit repo (init, then an unrelated update) is
    what both files need so a later commit reads as a real change instead of
    the initial commit.
    """

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "core.hooksPath", "/dev/null"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update readme"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        return tmp_path

    def test_detects_created_adr_under_docs_decisions(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every case in `TestMain` creates its ADR under `.agents/architecture`;
        without this one, a regression that narrowed scanning to that single
        directory would pass unnoticed.
        """
        adr_dir = git_repo / "docs" / "decisions"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002.md").write_text("# Docs Decisions ADR")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add docs decision adr"],
            cwd=str(git_repo),
            capture_output=True,
            check=True,
        )
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["HasChanges"] is True
        assert data["Created"] == ["docs/decisions/ADR-002.md"]
        assert data["RecommendedAction"] == "review"

    def test_include_untracked_counts_an_uncommitted_new_adr(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--include-untracked` surfaces a new ADR before it is ever committed.

        Without the flag an untracked file is invisible to a diff against
        `--since-commit`.
        """
        adr_dir = git_repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-099.md").write_text("# Untracked")
        exit_code = main(
            ["--base-path", str(git_repo), "--since-commit", "HEAD", "--include-untracked"]
        )
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["HasChanges"] is True
        assert any("ADR-099" in f for f in data["Created"])
