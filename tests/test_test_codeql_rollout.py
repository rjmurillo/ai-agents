"""Tests for test_codeql_rollout.py deployment validation script."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "test_codeql_rollout",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "test_codeql_rollout.py",
    ),
)
assert _spec is not None, "Failed to find test_codeql_rollout.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
ValidationTracker = _mod.ValidationTracker
check_configuration = _mod.check_configuration
check_gitignore = _mod.check_gitignore
main = _mod.main


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.output_format == "console"
        assert args.ci is False

    def test_json_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--format", "json"])
        assert args.output_format == "json"

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True


class TestValidationTracker:
    def test_add_passed_check(self) -> None:
        tracker = ValidationTracker()
        tracker.add("CLI", "test check", True, "details")
        assert tracker.total_checks == 1
        assert tracker.passed_checks == 1
        assert len(tracker.results["CLI"]) == 1

    def test_add_failed_check(self) -> None:
        tracker = ValidationTracker()
        tracker.add("CLI", "test check", False, "details")
        assert tracker.total_checks == 1
        assert tracker.passed_checks == 0

    def test_multiple_categories(self) -> None:
        tracker = ValidationTracker()
        tracker.add("CLI", "check1", True)
        tracker.add("Configuration", "check2", False)
        tracker.add("Scripts", "check3", True)
        assert tracker.total_checks == 3
        assert tracker.passed_checks == 2


class TestCheckConfiguration:
    def test_missing_configs(self) -> None:
        tracker = ValidationTracker()
        old_cwd = os.getcwd()
        try:
            os.chdir("/tmp")
            check_configuration(tracker)
        finally:
            os.chdir(old_cwd)
        config_results = tracker.results["Configuration"]
        assert any(not r["passed"] for r in config_results)

    def test_with_valid_config(self, tmp_path: Path) -> None:
        tracker = ValidationTracker()

        github_codeql = tmp_path / ".github" / "codeql"
        github_codeql.mkdir(parents=True)
        (github_codeql / "codeql-config.yml").write_text(
            "name: test\nqueries:\n  - q\n",
        )
        (github_codeql / "codeql-config-quick.yml").write_text(
            "name: quick\nqueries:\n  - q\n",
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            check_configuration(tracker)
        finally:
            os.chdir(old_cwd)

        config_results = tracker.results["Configuration"]
        shared_check = next(r for r in config_results if r["name"] == "Shared config")
        assert shared_check["passed"] is True


class TestCheckGitignore:
    def test_missing_gitignore(self) -> None:
        tracker = ValidationTracker()
        old_cwd = os.getcwd()
        try:
            os.chdir("/tmp")
            check_gitignore(tracker)
        finally:
            os.chdir(old_cwd)
        results = tracker.results["Gitignore"]
        assert any(not r["passed"] for r in results)

    def test_complete_gitignore(self, tmp_path: Path) -> None:
        tracker = ValidationTracker()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(
            ".codeql/cli/\n.codeql/db/\n.codeql/results/\n.codeql/logs/\n"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            check_gitignore(tracker)
        finally:
            os.chdir(old_cwd)

        results = tracker.results["Gitignore"]
        assert all(r["passed"] for r in results)


class TestMain:
    def test_returns_zero_on_pass(self) -> None:
        with (
            patch.object(_mod, "check_cli"),
            patch.object(_mod, "check_configuration"),
            patch.object(_mod, "check_scripts"),
            patch.object(_mod, "check_cicd"),
            patch.object(_mod, "check_local_dev"),
            patch.object(_mod, "check_automatic"),
            patch.object(_mod, "check_documentation"),
            patch.object(_mod, "check_tests"),
            patch.object(_mod, "check_gitignore"),
        ):
            result = main([])
            assert result == 0

    def test_ci_returns_one_on_fail(self) -> None:
        def fail_check(tracker):  # noqa: ANN001
            tracker.add("CLI", "fails", False, "forced failure")

        with (
            patch.object(_mod, "check_cli", side_effect=fail_check),
            patch.object(_mod, "check_configuration"),
            patch.object(_mod, "check_scripts"),
            patch.object(_mod, "check_cicd"),
            patch.object(_mod, "check_local_dev"),
            patch.object(_mod, "check_automatic"),
            patch.object(_mod, "check_documentation"),
            patch.object(_mod, "check_tests"),
            patch.object(_mod, "check_gitignore"),
        ):
            result = main(["--ci"])
            assert result == 1

    def test_json_output(self, capsys: pytest.CaptureFixture) -> None:
        with (
            patch.object(_mod, "check_cli"),
            patch.object(_mod, "check_configuration"),
            patch.object(_mod, "check_scripts"),
            patch.object(_mod, "check_cicd"),
            patch.object(_mod, "check_local_dev"),
            patch.object(_mod, "check_automatic"),
            patch.object(_mod, "check_documentation"),
            patch.object(_mod, "check_tests"),
            patch.object(_mod, "check_gitignore"),
        ):
            main(["--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "TotalChecks" in data
        assert "PassedChecks" in data
        assert "Status" in data
