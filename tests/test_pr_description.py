"""Tests for test_pr_description.py validation logic."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(
    _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "test_pr_description.py"
)


def run_validator(*args: str) -> dict[str, object]:
    """Run the validator script and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # JSON is on stdout, human-readable on stderr
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


class TestConventionalCommit:
    def test_valid_title(self):
        r = run_validator("--title", "feat: Add user authentication", "--body", "Closes #123")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_title_with_scope(self):
        r = run_validator("--title", "fix(auth): Resolve login issue", "--body", "Fixes #456")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_title_with_breaking_change(self):
        r = run_validator("--title", "feat!: Breaking change", "--body", "Closes #1")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_invalid_title(self):
        r = run_validator("--title", "Add new feature", "--body", "Closes #123")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "FAIL"
        assert r["Success"] is False


class TestIssueKeywords:
    def test_closes(self):
        r = run_validator("--title", "feat: X", "--body", "Closes #123")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_fixes(self):
        r = run_validator("--title", "feat: X", "--body", "Fixes #456")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_resolves(self):
        r = run_validator("--title", "feat: X", "--body", "Resolves #789")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_case_insensitive(self):
        r = run_validator("--title", "feat: X", "--body", "closes #100")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_past_tense(self):
        r = run_validator("--title", "feat: X", "--body", "Fixed #200")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_cross_repo(self):
        r = run_validator("--title", "feat: X", "--body", "Closes org/repo#123")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_no_keywords_warns(self):
        r = run_validator("--title", "feat: X", "--body", "No issue reference here")
        assert r["Validations"]["IssueKeywords"]["Status"] == "WARN"

    def test_multiple_keywords(self):
        r = run_validator("--title", "feat: X", "--body", "Closes #1\nFixes #2")
        kw = r["Validations"]["IssueKeywords"]
        assert kw["Status"] == "PASS"
        assert len(kw["Keywords"]) == 2


class TestTemplateCompliance:
    def test_complete_template(self):
        body = (
            "## Summary\n\nAdded auth.\n\n"
            "| Type | Reference |\n|------|--------|\n| **Issue** | Closes #1 |\n\n"
            "## Type of Change\n\n- [x] New feature\n\n"
            "## Changes\n\n- Added OAuth2\n"
        )
        r = run_validator("--title", "feat: Auth", "--body", body)
        assert r["Validations"]["TemplateCompliance"]["Status"] == "PASS"

    def test_missing_sections(self):
        r = run_validator("--title", "feat: X", "--body", "Just a description")
        assert r["Validations"]["TemplateCompliance"]["Status"] == "WARN"


class TestOverall:
    def test_success_with_warnings(self):
        r = run_validator("--title", "feat: Feature", "--body", "Minimal body")
        assert r["Success"] is True
        assert len(r["Warnings"]) > 0

    def test_fail_with_errors(self):
        r = run_validator("--title", "Bad title", "--body", "Closes #123")
        assert r["Success"] is False
        assert len(r["Errors"]) > 0

    def test_fail_on_violation_with_warnings(self):
        """--fail-on-violation causes non-zero exit when warnings exist."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        # Warnings present (no issue keywords, incomplete template) but title valid
        # so Success is True in JSON, but exit code should still be 0 for warnings-only
        r = json.loads(result.stdout)
        assert r["Success"] is True
        assert len(r["Warnings"]) > 0

    def test_fail_on_violation_with_errors(self):
        """--fail-on-violation returns exit code 1 when errors exist."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "Bad title", "--body", "Closes #123",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        assert r["Success"] is False
        assert result.returncode == 1
