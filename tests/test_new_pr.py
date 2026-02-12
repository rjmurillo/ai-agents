"""Tests for new_pr.py skill script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


_mod = _import_script("new_pr")
main = _mod.main
build_parser = _mod.build_parser
validate_conventional_commit = _mod.validate_conventional_commit
get_repo_root = _mod.get_repo_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_title_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--title", "feat: test", "--base", "main"])
        assert args.title == "feat: test"
        assert args.base == "main"

    def test_draft_flag(self):
        args = build_parser().parse_args(["--title", "fix: bug", "--draft"])
        assert args.draft is True

    def test_skip_validation_flag(self):
        args = build_parser().parse_args([
            "--title", "fix: bug", "--skip-validation", "--audit-reason", "emergency",
        ])
        assert args.skip_validation is True
        assert args.audit_reason == "emergency"


# ---------------------------------------------------------------------------
# Tests: validate_conventional_commit
# ---------------------------------------------------------------------------


class TestValidateConventionalCommit:
    def test_valid_feat(self):
        assert validate_conventional_commit("feat: add new feature") is True

    def test_valid_fix_with_scope(self):
        assert validate_conventional_commit("fix(auth): resolve login issue") is True

    def test_valid_breaking_change(self):
        assert validate_conventional_commit("feat!: breaking change") is True

    def test_invalid_format(self):
        assert validate_conventional_commit("Update something") is False

    def test_invalid_type(self):
        assert validate_conventional_commit("update: something") is False


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_gh_not_installed_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=1),  # gh --version
            ],
        ):
            rc = main(["--title", "feat: test"])
        assert rc == 2

    def test_invalid_title_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
            ],
        ):
            rc = main(["--title", "Bad title format"])
        assert rc == 2

    def test_skip_validation_without_reason_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
            ],
        ):
            rc = main(["--title", "feat: test", "--skip-validation"])
        assert rc == 2

    def test_successful_pr_creation(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
                _completed(stdout="", rc=0),  # git diff (validations)
                _completed(rc=0),  # gh pr create
            ],
        ):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 0

    def test_body_file_not_found_returns_2(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
                _completed(stdout="", rc=0),  # git diff
            ],
        ):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch",
                "--body-file", "/nonexistent/file.md",
            ])
        assert rc == 2
