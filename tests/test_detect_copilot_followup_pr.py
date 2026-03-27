"""Tests for detect_copilot_followup_pr.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("detect_copilot_followup_pr")
main = _mod.main
build_parser = _mod.build_parser
# Alias to avoid pytest collecting this as a test function
check_followup_pattern = _mod.test_followup_pattern
compare_diff_content = _mod.compare_diff_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pr_number_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pr-number", "42"])
        assert args.pr_number == 42


# ---------------------------------------------------------------------------
# Tests: test_followup_pattern
# ---------------------------------------------------------------------------


class TestFollowupPattern:
    def test_matches_copilot_branch(self):
        pr = {"headRefName": "copilot/sub-pr-42"}
        assert check_followup_pattern(pr) is True

    def test_matches_specific_original_pr(self):
        pr = {"headRefName": "copilot/sub-pr-42"}
        assert check_followup_pattern(pr, 42) is True

    def test_rejects_different_original_pr(self):
        pr = {"headRefName": "copilot/sub-pr-42"}
        assert check_followup_pattern(pr, 99) is False

    def test_rejects_non_copilot_branch(self):
        pr = {"headRefName": "feat/something"}
        assert check_followup_pattern(pr) is False

    def test_rejects_branch_with_suffix(self):
        pr = {"headRefName": "copilot/sub-pr-42-extra"}
        assert check_followup_pattern(pr) is False


# ---------------------------------------------------------------------------
# Tests: compare_diff_content
# ---------------------------------------------------------------------------


class TestCompareDiffContent:
    def test_empty_diff_is_duplicate(self):
        result = compare_diff_content("o", "r", "", [], 42)
        assert result["category"] == "DUPLICATE"

    def test_no_overlap_is_independent(self):
        diff = "diff --git a/new_file.py b/new_file.py\n+something"
        result = compare_diff_content("o", "r", diff, [], 0)
        assert result["category"] == "INDEPENDENT"

    def test_high_overlap_is_duplicate(self):
        diff = (
            "diff --git a/file1.py b/file1.py\n+change\n"
            "diff --git a/file2.py b/file2.py\n+change"
        )
        commits = [
            {"changedFiles": ["file1.py", "file2.py"]},
        ]
        result = compare_diff_content("o", "r", diff, commits, 0)
        assert result["category"] == "DUPLICATE"
        assert result["similarity"] >= 80


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "detect_copilot_followup_pr.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pr-number", "1"])
            assert exc.value.code == 4

    def test_no_followups_found(self, capsys):
        with patch(
            "detect_copilot_followup_pr.assert_gh_authenticated",
        ), patch(
            "detect_copilot_followup_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ):
            rc = main(["--pr-number", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["found"] is False
