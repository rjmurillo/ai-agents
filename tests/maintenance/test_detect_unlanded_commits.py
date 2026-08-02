"""Tests for detect_unlanded_commits.py.

Covers:
- scan returns empty when all branches are ancestors of base
- scan returns an entry when a branch tip is not an ancestor
- commit_count is accurate
- main exits 0 on no findings, 1 on findings
- check_github filter skips branches whose PR is not confirmed merged
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from scripts.maintenance.detect_unlanded_commits import (
    UnlandedBranch,
    _commit_count_not_in_base,
    _is_ancestor,
    _tip_sha,
    main,
    scan,
)


def _make_run(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class TestIsAncestor:
    def test_returns_true_when_git_exits_zero(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(0)
            assert _is_ancestor("abc123", "origin/main", "/repo") is True

    def test_returns_false_when_git_exits_one(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(1)
            assert _is_ancestor("abc123", "origin/main", "/repo") is False


class TestTipSha:
    def test_returns_sha_on_success(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(0, stdout="deadbeef\n")
            assert _tip_sha("origin/fix/thing", "/repo") == "deadbeef"

    def test_returns_empty_on_failure(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(128, stdout="")
            assert _tip_sha("origin/missing", "/repo") == ""


class TestCommitCount:
    def test_returns_count(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(0, stdout="3\n")
            assert _commit_count_not_in_base("origin/fix/thing", "origin/main", "/repo") == 3

    def test_returns_zero_on_git_error(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(128, stdout="")
            assert _commit_count_not_in_base("origin/fix/thing", "origin/main", "/repo") == 0

    def test_returns_zero_on_non_integer_stdout(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(0, stdout="not-a-number\n")
            assert _commit_count_not_in_base("origin/fix/thing", "origin/main", "/repo") == 0


class TestScan:
    def _mock_git_responses(self, branches: list[str], tip: str, count: int) -> MagicMock:
        def side_effect(args: list[str], _repo: str) -> MagicMock:
            if args[0] == "branch":
                return _make_run(0, stdout="\n".join(branches) + "\n")
            if args[0] == "rev-parse":
                return _make_run(0, stdout=tip + "\n")
            if args[0] == "rev-list":
                return _make_run(0, stdout=str(count) + "\n")
            return _make_run(0)

        return side_effect

    def test_returns_empty_when_no_branches(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits._git") as mock:
            mock.return_value = _make_run(0, stdout="")
            result = scan("/repo", "origin/main", check_github=False)
        assert result == []

    def test_returns_entry_when_branch_has_unlanded_commits(self) -> None:
        side = self._mock_git_responses(["origin/fix/thing"], "deadbeef", 2)
        with patch("scripts.maintenance.detect_unlanded_commits._git", side_effect=side):
            result = scan("/repo", "origin/main", check_github=False)
        assert len(result) == 1
        assert result[0].branch == "origin/fix/thing"
        assert result[0].commit_count == 2

    def test_skips_branch_with_zero_commits(self) -> None:
        side = self._mock_git_responses(["origin/fix/zero"], "deadbeef", 0)
        with patch("scripts.maintenance.detect_unlanded_commits._git", side_effect=side):
            result = scan("/repo", "origin/main", check_github=False)
        assert result == []

    def test_check_github_skips_unmerged_pr(self) -> None:
        side = self._mock_git_responses(["origin/fix/thing"], "deadbeef", 1)
        with (
            patch("scripts.maintenance.detect_unlanded_commits._git", side_effect=side),
            patch(
                "scripts.maintenance.detect_unlanded_commits._branch_pr_merged",
                return_value=False,
            ),
        ):
            result = scan("/repo", "origin/main", check_github=True)
        assert result == []

    def test_check_github_includes_merged_pr(self) -> None:
        side = self._mock_git_responses(["origin/fix/thing"], "deadbeef", 1)
        with (
            patch("scripts.maintenance.detect_unlanded_commits._git", side_effect=side),
            patch(
                "scripts.maintenance.detect_unlanded_commits._branch_pr_merged",
                return_value=True,
            ),
        ):
            result = scan("/repo", "origin/main", check_github=True)
        assert len(result) == 1


class TestMain:
    def test_exits_zero_when_no_findings(self) -> None:
        with patch("scripts.maintenance.detect_unlanded_commits.scan", return_value=[]):
            assert main(["--repo", "."]) == 0

    def test_exits_one_when_findings_exist(self) -> None:
        findings = [UnlandedBranch("origin/fix/thing", "deadbeef123456", 1)]
        with patch("scripts.maintenance.detect_unlanded_commits.scan", return_value=findings):
            assert main(["--repo", "."]) == 1

    def test_exits_two_on_exception(self) -> None:
        with patch(
            "scripts.maintenance.detect_unlanded_commits.scan", side_effect=RuntimeError("boom")
        ):
            assert main(["--repo", "."]) == 2
