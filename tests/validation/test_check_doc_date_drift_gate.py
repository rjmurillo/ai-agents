"""Gate behaviour: scope, outcome type, CLI exit codes, and ``--tree``."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts.validation import check_doc_date_drift as checker
from scripts.validation.evidence import EvidenceState, pre_pr_policy
from tests.validation.doc_date_drift_helpers import (
    cite,
    commit_head,
    make_repo,
    run_cli,
)

DOC = "docs/COST-GOVERNANCE.md"
BAD_HEADER = "**Last Updated**: 2026-10-24\n**Next Review**: 2026-10-01\n"
GOOD_HEADER = "**Last Updated**: 2026-10-24\n**Next Review**: 2027-01-22\n"


class TestScope:
    @pytest.mark.parametrize(
        "path",
        [
            ".project-toolkit/retrospective/2026-01-01-x.md",
            ".project-toolkit/memory/episodes/x.md",
            "docs/fixtures/header.md",
            "src/claude/rules/x.md",
            "src/claude/skills/quota/SKILL.md",
            ".claude/skills/quota/SKILL.md",
            "docs/notes.txt",
        ],
    )
    def test_out_of_scope_paths(self, path: str) -> None:
        assert checker.is_out_of_scope(path)

    @pytest.mark.parametrize(
        "path",
        [
            "docs/COST-GOVERNANCE.md",
            "templates/skills/quota.SKILL.md.tmpl",
            "src/claude/skills/quota/references/notes.md",
        ],
    )
    def test_in_scope_paths(self, path: str) -> None:
        assert not checker.is_out_of_scope(path)

    def test_added_lines_in_a_generated_skill_md_are_not_read(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {"src/claude/skills/quota/SKILL.md": BAD_HEADER})
        assert checker.main(["--repo-root", str(root), "--base", "main"]) == 0


class TestCli:
    def test_findings_exit_one_and_print_both_locations_and_the_suggestion(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: BAD_HEADER})
        code, out = run_cli(root, capsys)
        assert code == 1
        assert cite(DOC, 2) in out
        assert f"{DOC}:1" in out
        assert "header-pair" in out
        assert "2027-01-22" in out

    def test_clean_run_exits_zero_and_prints_the_examined_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: GOOD_HEADER})
        code, out = run_cli(root, capsys)
        assert code == 0
        assert "examined 2 line(s) across 1 file(s)" in out

    def test_a_non_repository_exits_two(self, tmp_path: Path) -> None:
        assert checker.main(["--repo-root", str(tmp_path)]) == 2

    def test_a_git_failure_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: BAD_HEADER})
        with mock.patch.object(checker, "_head_tracked_paths", return_value=None):
            code, _ = run_cli(root, capsys)
        assert code == 2

    def test_an_unresolvable_base_prints_skip_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_repo(tmp_path)
        with mock.patch.object(checker, "_resolve_default_base_ref", return_value=None):
            code = checker.main(["--repo-root", str(root)])
        assert code == 0
        assert "[SKIP]" in capsys.readouterr().out


class TestTreeMode:
    def test_tree_reports_the_backlog_at_head(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_repo(tmp_path, {DOC: BAD_HEADER})
        code = checker.main(["--repo-root", str(root), "--tree"])
        out = capsys.readouterr().out
        assert code == 1
        assert "every line at HEAD" in out
        assert cite(DOC, 2) in out

    def test_tree_reports_a_symmetric_pair_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        url = "https://example.org/a/b"
        base = {
            "docs/skills/quota.md": f'See "Quota Guide" {url} (updated 2024).\n',
            "src/claude/skills/quota/references/q.md": f'See "Quota Guide" {url} (updated 2025).\n',
        }
        root = make_repo(tmp_path, base)
        code = checker.main(["--repo-root", str(root), "--tree"])
        out = capsys.readouterr().out
        assert code == 1
        assert "1 finding(s)" in out
        assert cite("docs/skills/quota.md", 1) in out
        assert "Suggested value: 2025" in out


class TestAdvisoryOutcome:
    def test_findings_are_a_licensed_warning_not_a_blocking_failure(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: BAD_HEADER})
        with mock.patch.object(checker, "_resolve_default_base_ref", return_value="main"):
            outcome = checker.validate_doc_date_drift(root)
        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "advisory.findings"
        assert outcome.findings == 1
        assert pre_pr_policy().accepts(outcome)

    def test_a_clean_run_passes_with_the_examined_count(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_head(root, {DOC: GOOD_HEADER})
        with mock.patch.object(checker, "_resolve_default_base_ref", return_value="main"):
            outcome = checker.validate_doc_date_drift(root)
        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 2

    def test_no_base_ref_is_a_skip_that_passes_the_policy(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        with mock.patch.object(checker, "_resolve_default_base_ref", return_value=None):
            outcome = checker.validate_doc_date_drift(root)
        assert outcome.state is EvidenceState.SKIP
        assert pre_pr_policy().accepts(outcome)

    def test_a_git_failure_is_blocked_and_licensed(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        with (
            mock.patch.object(checker, "_resolve_default_base_ref", return_value="main"),
            mock.patch.object(checker, "_head_tracked_paths", return_value=None),
        ):
            outcome = checker.validate_doc_date_drift(root)
        assert outcome.state is EvidenceState.BLOCKED
        assert pre_pr_policy().accepts(outcome)


class TestCommitDate:
    def test_the_head_commit_date_is_read_with_git(self, tmp_path: Path) -> None:
        root = make_repo(tmp_path)
        commit_date = checker.head_commit_date(root)
        assert commit_date is not None
        assert commit_date.isoformat() == "2026-10-24"

    def test_a_repository_with_no_commits_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, timeout=60)
        assert checker.head_commit_date(root) is None
