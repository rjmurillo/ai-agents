"""Tests for extract_github_context.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "utils"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("extract_github_context")
main = _mod.main
_extract = _mod._extract_context


class TestExtractContext:
    def test_pr_pattern(self):
        result = _extract("Review PR 806 comments")
        assert 806 in result["pr_numbers"]

    def test_pr_hash_pattern(self):
        result = _extract("Review PR #806")
        assert 806 in result["pr_numbers"]

    def test_pull_request_pattern(self):
        result = _extract("pull request 123")
        assert 123 in result["pr_numbers"]

    def test_issue_pattern(self):
        result = _extract("Fix issue #45")
        assert 45 in result["issue_numbers"]

    def test_github_url_pr(self):
        result = _extract("Check https://github.com/owner/repo/pull/123")
        assert 123 in result["pr_numbers"]
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"

    def test_github_url_issue(self):
        result = _extract("See https://github.com/org/proj/issues/456")
        assert 456 in result["issue_numbers"]
        assert result["owner"] == "org"

    def test_standalone_hash(self):
        result = _extract("Check #42")
        assert 42 in result["pr_numbers"]

    def test_no_context(self):
        result = _extract("Hello world")
        assert result["pr_numbers"] == []
        assert result["issue_numbers"] == []
        assert result["owner"] is None

    def test_multiple_patterns(self):
        result = _extract("PR 10 and issue #20 and #30")
        assert 10 in result["pr_numbers"]
        assert 20 in result["issue_numbers"]

    def test_url_doesnt_duplicate(self):
        result = _extract("https://github.com/o/r/pull/5")
        assert result["pr_numbers"].count(5) == 1


class TestCLI:
    def test_happy_path(self, capsys):
        rc = main(["--text", "Review PR 42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert 42 in output["pr_numbers"]

    def test_require_pr_success(self, capsys):
        rc = main(["--text", "PR 1", "--require-pr"])
        assert rc == 0

    def test_require_pr_failure(self):
        rc = main(["--text", "No context here", "--require-pr"])
        assert rc == 1

    def test_require_issue_failure(self):
        rc = main(["--text", "No context", "--require-issue"])
        assert rc == 1

    def test_require_issue_success(self, capsys):
        rc = main(["--text", "issue #5", "--require-issue"])
        assert rc == 0
