"""Tests for ai-review context construction."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/ci/build_ai_review_context.py"


def _import_script():
    spec = importlib.util.spec_from_file_location("build_ai_review_context", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_ai_review_context"] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script()
CommandResult = _mod.CommandResult
ReviewContext = _mod.ReviewContext


def test_builds_full_pr_context(monkeypatch: pytest.MonkeyPatch):
    """Small PR diffs become full context with title and body."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[-1] == ".title":
            return CommandResult('Fix `$bad" title\\\\\n', "", 0)
        if arguments[-1] == ".number":
            return CommandResult("7\n", "", 0)
        if arguments[-1] == ".body":
            return CommandResult("Body text\n", "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/file b/file\n+change\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "full"
    assert context.infrastructure_failure is False
    assert "## PR #7: Fix bad title" in context.text
    assert "## PR Description\nBody text" in context.text
    assert "diff --git" in context.text


def test_marks_pr_number_mismatch_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Wrong PR data fails closed for downstream parsing."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[-1] == ".title":
            return CommandResult("Mismatch\n", "", 0)
        if arguments[-1] == ".number":
            return CommandResult("8\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "Could not fetch PR #7" in context.text


def test_large_pr_uses_file_list_summary(monkeypatch: pytest.MonkeyPatch):
    """Diff size failures degrade to a file-list summary."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("src/a.py\nsrc/b.py", False),
    )

    context = _mod.build_large_pr_context("7", "owner/repo")

    assert context.mode == "summary"
    assert ">300 files" in context.text
    assert "src/a.py" in context.text
    assert "src/b.py" in context.text


def test_large_pr_raises_when_all_fallbacks_fail(monkeypatch: pytest.MonkeyPatch):
    """An unreadable large PR returns a nonzero script path."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("", False),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda pr_number, repository: "")

    with pytest.raises(SystemExit) as exc:
        _mod.build_large_pr_context("7", "owner/repo")

    assert exc.value.code == 1


def test_paginated_file_list_marks_later_api_failure_as_truncated(
    monkeypatch: pytest.MonkeyPatch,
):
    """A later page failure returns the pages already fetched and marks truncation."""

    first_page = "\n".join(f"src/file_{index}.py" for index in range(_mod.FILES_PER_PAGE))
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        if "&page=1" in arguments[1]:
            return CommandResult(first_page, "", 0)
        if "&page=2" in arguments[1]:
            return CommandResult("", "api unavailable", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    file_list, truncated = _mod.get_paginated_file_list("7", "owner/repo")

    assert truncated is True
    assert file_list == first_page
    assert len(calls) == 2


def test_build_spec_context_without_pr_uses_spec_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Spec context can be built when no PR diff is available by design."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: pytest.fail(
            f"unexpected gh call: {arguments}"
        ),
    )

    context = _mod.build_spec_context(str(spec_path), "", "owner/repo", 100)

    assert context.mode == "partial"
    assert "## Specification\nSpec body" in context.text
    assert "## Implementation Changes\n[No PR diff provided]" in context.text


def test_build_spec_context_truncates_large_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Large spec diffs keep the review context under the configured line limit."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    diff = "line 1\nline 2\nline 3\nline 4\n"

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult(diff, "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 2)

    assert context.mode == "partial"
    assert "[Diff truncated to first 2 of 4 lines]" in context.text
    assert "line 1\nline 2" in context.text
    assert "line 3" not in context.text


def test_build_spec_context_falls_back_to_file_list_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Unavailable spec diffs degrade to a file-list summary."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "",
            "diff unavailable",
            1,
        ),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda pr_number, repository: "scripts/ci/build_ai_review_context.py",
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "summary"
    assert "[Diff unavailable, showing file list only]" in context.text
    assert "scripts/ci/build_ai_review_context.py" in context.text


def test_build_spec_context_uses_stdout_from_nonzero_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """A nonzero gh diff still uses stdout when GitHub emitted a usable diff."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "diff --git a/spec.md b/spec.md\n+change\n",
            "warning",
            1,
        ),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda pr_number, repository: pytest.fail("name-only fallback should not run"),
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "full"
    assert "diff --git a/spec.md b/spec.md" in context.text


def test_build_spec_context_reports_unavailable_when_diff_and_file_list_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Spec context names the missing diff when no fallback data exists."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "",
            "diff unavailable",
            1,
        ),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda pr_number, repository: "")

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "summary"
    assert "## Implementation Changes\n[Diff unavailable]" in context.text


def test_write_outputs_uses_runner_temp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """GitHub outputs include the context file and multiline payload."""

    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("PR_NUMBER", "7")

    _mod.write_outputs(ReviewContext("hello\nworld", "summary", True))

    output = output_path.read_text(encoding="utf-8")
    context_file = runner_temp / "ai-review-context-pr7.txt"
    assert context_file.read_text(encoding="utf-8") == "hello\nworld"
    assert "context_mode=summary" in output
    assert f"context_file={context_file}" in output
    assert "context_infra_failure=true" in output
    assert "context_built<<EOF_CONTEXT_BUILT\nhello\nworld\nEOF_CONTEXT_BUILT" in output


def test_append_multiline_output_uses_collision_free_delimiter(tmp_path: Path):
    """GitHub output delimiters cannot be injected through PR-controlled text."""

    output_path = tmp_path / "github-output.txt"

    _mod.append_multiline_output(
        output_path,
        "context_built",
        "safe line\nEOF_CONTEXT_BUILT\ncontext_mode=full",
    )

    output = output_path.read_text(encoding="utf-8")
    assert "context_built<<EOF_CONTEXT_BUILT_1" in output
    assert output.endswith("\nEOF_CONTEXT_BUILT_1\n")
