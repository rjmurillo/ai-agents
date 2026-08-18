"""Tests for issue #5129: docs-only QA skip scope verification.

The bug: ``validate_qa_skip_scope`` unconditionally rejected the documented
``SKIPPED: docs-only`` evidence value with a fixed error, regardless of
whether the staged commit range actually qualified. This is the docs-only
counterpart to ``test_investigation_eligibility.py``: every changed file
must be a Markdown file, and its code-block content must be byte-identical
between the base and head revisions, per ``.agents/SESSION-PROTOCOL.md``'s
"docs-only" definition (editorial changes only, no code, configuration,
tests, workflows, or code block changes).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "session"
    / "scripts"
    / "test_docs_only_eligibility.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("test_docs_only_eligibility", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _run_script(base_ref: str, head_ref: str, cwd: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--base-ref", base_ref, "--head-ref", head_ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(["init", "-b", "main"], repo_dir)
    _git(["config", "user.email", "test@example.com"], repo_dir)
    _git(["config", "user.name", "Test"], repo_dir)
    (repo_dir / "README.md").write_text("# Title\n\nOriginal prose.\n")
    _git(["add", "."], repo_dir)
    _git(["commit", "-m", "init"], repo_dir)
    return repo_dir


class TestUnitCodeBlockDetection:
    """Direct unit tests for _code_block_lines."""

    def test_fenced_block_is_detected(self):
        mod = _load_module()
        markdown = "prose\n```python\nx = 1\n```\nmore prose\n"
        lines = mod._code_block_lines(markdown)
        assert lines == ["```python", "x = 1", "```"]

    def test_tilde_fence_is_detected(self):
        mod = _load_module()
        markdown = "prose\n~~~\ncode\n~~~\n"
        lines = mod._code_block_lines(markdown)
        assert lines == ["~~~", "code", "~~~"]

    def test_indented_code_is_detected(self):
        mod = _load_module()
        markdown = "prose\n    indented code\nmore prose\n"
        lines = mod._code_block_lines(markdown)
        assert lines == ["    indented code"]

    def test_prose_only_yields_no_code_lines(self):
        mod = _load_module()
        markdown = "# Title\n\nJust prose, with `inline code` spans.\n"
        assert mod._code_block_lines(markdown) == []

    def test_unterminated_fence_runs_to_eof(self):
        mod = _load_module()
        markdown = "prose\n```\ncode forever\n"
        lines = mod._code_block_lines(markdown)
        # The trailing "" is the split() artifact of the file's final
        # newline, itself inside the still-open fence, and is part of the
        # extracted content, not a defect.
        assert lines == ["```", "code forever", ""]


class TestEligibleEditorialChange:
    """Positive: a pure prose edit to a Markdown file is eligible."""

    def test_editorial_only_change_is_eligible(self, repo: Path):
        start = _git(["rev-parse", "HEAD"], repo)
        (repo / "README.md").write_text("# Title\n\nRevised prose, fixed a typo.\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "docs: fix typo"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is True
        assert payload["Violations"] == []

    def test_new_markdown_file_with_no_code_is_eligible(self, repo: Path):
        start = _git(["rev-parse", "HEAD"], repo)
        (repo / "NOTES.md").write_text("# Notes\n\nJust prose.\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "docs: add notes"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is True


class TestIneligibleChanges:
    """Negative: non-doc files and code-block edits are ineligible."""

    def test_non_markdown_file_is_a_violation(self, repo: Path):
        start = _git(["rev-parse", "HEAD"], repo)
        (repo / "script.py").write_text("x = 1\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "add script"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is False
        assert any(
            "script.py" in v and "not a documentation file" in v
            for v in payload["Violations"]
        )

    def test_code_block_content_change_is_a_violation(self, repo: Path):
        (repo / "README.md").write_text("# Title\n\n```python\nx = 1\n```\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "add code sample"], repo)
        start = _git(["rev-parse", "HEAD"], repo)

        (repo / "README.md").write_text("# Title\n\n```python\nx = 2\n```\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "docs: edit example"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is False
        assert any(
            "README.md" in v and "code block content changed" in v
            for v in payload["Violations"]
        )

    def test_prose_edit_around_unchanged_code_block_is_eligible(self, repo: Path):
        (repo / "README.md").write_text("# Title\n\n```python\nx = 1\n```\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "add code sample"], repo)
        start = _git(["rev-parse", "HEAD"], repo)

        (repo / "README.md").write_text(
            "# Title, revised\n\n```python\nx = 1\n```\n\nMore prose.\n"
        )
        _git(["add", "."], repo)
        _git(["commit", "-m", "docs: expand prose"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is True

    def test_new_markdown_file_with_code_is_ineligible(self, repo: Path):
        start = _git(["rev-parse", "HEAD"], repo)
        (repo / "GUIDE.md").write_text("# Guide\n\n```bash\necho hi\n```\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "docs: add guide with example"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        payload = _run_script(start, head, repo)
        assert payload["Eligible"] is False
        assert any("GUIDE.md" in v for v in payload["Violations"])


class TestNegativePaths:
    """Negative: errors and edge cases fail closed."""

    def test_invalid_base_ref(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--base-ref", "not-a-sha", "--head-ref", "a" * 40],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["Eligible"] is False
        assert "Invalid base ref" in payload.get("Error", "")

    def test_invalid_head_ref(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--base-ref", "a" * 40, "--head-ref", "not-a-sha"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["Eligible"] is False
        assert "Invalid head ref" in payload.get("Error", "")

    def test_nonexistent_commit_fails_closed(self, repo: Path):
        head = _git(["rev-parse", "HEAD"], repo)
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--base-ref", "0" * 40, "--head-ref", head],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["Eligible"] is False
        assert payload.get("Error")
