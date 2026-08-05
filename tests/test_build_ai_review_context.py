"""Tests for ai-review context construction."""

from __future__ import annotations

import importlib.util
import json
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


def _pulls_payload(number: int, title: str, body: str) -> str:
    """One REST pulls response, the shape fetch_pr_metadata reads."""
    return json.dumps({"number": number, "title": title, "body": body})


def test_builds_full_pr_context(monkeypatch: pytest.MonkeyPatch):
    """Small PR diffs become full context with title and body."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(
                _pulls_payload(7, 'Fix `$bad" title\\\\', "Body text"), "", 0
            )
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
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(8, "Mismatch", ""), "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "Could not fetch PR #7" in context.text


def test_marks_rate_limited_empty_diff_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """A 403 that empties the diff must take the DID_NOT_RUN infra path.

    Issue #4547: the rate-limit 403 raised ExternalGhError, which exits 3 and
    fails the composite step. Every later step, including the infra gate that
    writes the DID_NOT_RUN verdict, was then skipped, so the verdict file was
    never written. Downstream read an empty verdict and defaulted to
    NEEDS_REVIEW with INFRA_FAILURE recorded as false, which is
    indistinguishable from a real finding and blocked the PR on a transient
    error.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Rate limited", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult(
                "",
                "could not find pull request diff: HTTP 403: API rate limit "
                "exceeded for user ID 6811113.",
                1,
            )
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert context.mode == "error"
    assert "INFRASTRUCTURE_FAILURE" in context.text
    # The observed error must survive into the context so a reader can tell a
    # rate limit apart from a permissions problem without opening the raw log.
    assert "403" in context.text
    assert "rate limit" in context.text


def test_marks_empty_diff_with_no_stderr_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """An empty diff with a silent gh failure still fails closed, not exit 3."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Silent", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "Failed to fetch PR diff" in context.text


def test_empty_diff_no_longer_raises_external_gh_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Pin the regression directly: exit 3 bypasses the infra gate entirely.

    This is the vacuity guard for the two tests above. If the raise is ever
    restored, those tests would error out rather than fail on an assertion, so
    this test names the exception type explicitly.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "NoRaise", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "boom", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    try:
        _mod.build_pr_diff_context("7", "owner/repo", 100)
    except _mod.ExternalGhError as exc:  # pragma: no cover - regression guard
        raise AssertionError(
            "an empty diff must not raise ExternalGhError; exit 3 skips the "
            f"infra gate and no verdict file is written (issue #4547): {exc}"
        ) from exc


def test_large_pr_uses_file_list_summary(monkeypatch: pytest.MonkeyPatch):
    """Diff size failures degrade to a file-list summary."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("src/a.py\nsrc/b.py", False, False),
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
        lambda pr_number, repository: ("", False, True),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda pr_number, repository: "")

    with pytest.raises(_mod.ExternalGhError):
        _mod.build_large_pr_context("7", "owner/repo")


def test_get_pr_name_only_uses_stdout_from_nonzero_diff(
    monkeypatch: pytest.MonkeyPatch,
):
    """A nonzero gh name-only call still uses stdout when GitHub emitted filenames."""

    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "src/a.py\nsrc/b.py\n",
            "warning",
            1,
        ),
    )

    assert _mod.get_pr_name_only("7", "owner/repo") == "src/a.py\nsrc/b.py"


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

    file_list, truncated, api_failed = _mod.get_paginated_file_list("7", "owner/repo")

    assert truncated is True
    assert api_failed is True
    assert file_list == first_page
    assert len(calls) == 2


def test_large_pr_warns_api_failure_without_max_page_limit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Partial API results name the fetch failure instead of the max-page limit."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("src/a.py\nsrc/b.py", True, True),
    )

    context = _mod.build_large_pr_context("7", "owner/repo")

    output = capsys.readouterr().out
    assert context.mode == "summary"
    assert "GitHub API pagination failed" in output
    assert "truncated at 500 files" not in output


def test_build_issue_context_fetches_issue_details(monkeypatch: pytest.MonkeyPatch):
    """Issue context uses gh issue data as review input."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        assert arguments[:5] == ["issue", "view", "2814", "--repo", "owner/repo"]
        return CommandResult("Title: ADR-006\n\nBody:\nExtract YAML logic\n\nLabels: ci", "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_issue_context("2814", "owner/repo")

    assert context.mode == "full"
    assert "Title: ADR-006" in context.text
    assert "Labels: ci" in context.text


def test_build_issue_context_without_issue_number_skips_gh(
    monkeypatch: pytest.MonkeyPatch,
):
    """Missing issue input returns local context without hitting GitHub."""

    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: pytest.fail(
            f"unexpected gh call: {arguments}"
        ),
    )

    context = _mod.build_issue_context("", "")

    assert context.mode == "partial"
    assert context.text == "No issue number provided"


def test_build_issue_context_requires_repository() -> None:
    """Issue context needs explicit repo routing for gh calls."""

    with pytest.raises(_mod.ConfigError, match="GITHUB_REPOSITORY"):
        _mod.build_issue_context("2814", "")


def test_build_session_log_context_reads_file(tmp_path: Path):
    """Session-log context reads the requested file with UTF-8 decoding."""

    session_path = tmp_path / "session.json"
    session_path.write_text('{"endingCommit":"abc"}', encoding="utf-8")

    context = _mod.build_session_log_context(str(session_path))

    assert context.mode == "full"
    assert context.text == '{"endingCommit":"abc"}'


def test_build_session_log_context_reports_missing(tmp_path: Path):
    """Missing session logs produce an explicit review context."""

    missing_path = tmp_path / "missing.json"

    context = _mod.build_session_log_context(str(missing_path))

    assert context.mode == "partial"
    assert context.text == f"Session log file not found: {missing_path}"


def test_invalid_session_log_encoding_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Non-UTF-8 session logs map to the repository config exit code."""

    session_path = tmp_path / "session.json"
    session_path.write_bytes(b"\xff")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "session-log")
    monkeypatch.setenv("CONTEXT_PATH", str(session_path))

    assert _mod.main() == 2
    assert "Session log file must be UTF-8" in capsys.readouterr().err


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


def test_build_spec_context_reports_missing_as_partial(tmp_path: Path):
    """Missing spec files do not claim full review context."""

    missing_path = tmp_path / "missing.md"

    context = _mod.build_spec_context(str(missing_path), "", "owner/repo", 100)

    assert context.mode == "partial"
    assert context.text == f"Spec file not found: {missing_path}"


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


def test_invalid_spec_encoding_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Non-UTF-8 spec files map to the repository config exit code."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_bytes(b"\xff")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "spec-file")
    monkeypatch.setenv("CONTEXT_PATH", str(spec_path))
    monkeypatch.delenv("PR_NUMBER", raising=False)

    assert _mod.main() == 2
    assert "Spec file must be UTF-8" in capsys.readouterr().err


def test_pr_diff_context_requires_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """PR diff context fails with a config error when repository is missing."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert _mod.main() == 2
    assert "GITHUB_REPOSITORY is required for pr-diff context" in capsys.readouterr().err


def test_pr_diff_context_requires_pr_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """PR diff context must fail closed when no PR number is available."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    assert _mod.main() == 2
    assert "PR_NUMBER is required for pr-diff context" in capsys.readouterr().err


def test_issue_context_gh_failure_is_partial(monkeypatch: pytest.MonkeyPatch):
    """Issue lookup failures must not claim full context."""

    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult("", "fail", 1),
    )

    context = _mod.build_issue_context("2814", "owner/repo")

    assert context.mode == "partial"
    assert context.text == "Unable to get issue"


def test_unknown_context_type_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Unknown context types must fail closed instead of unlocking PASS."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "typo")

    assert _mod.main() == 2
    assert "Unknown CONTEXT_TYPE: typo" in capsys.readouterr().err


def test_main_maps_external_gh_error_to_external_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """GitHub outages must report the repository external exit code."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: (_ for _ in ()).throw(_mod.ExternalGhError("gh unavailable")),
    )

    assert _mod.main() == 3
    assert "::error::gh unavailable" in capsys.readouterr().err


def test_main_exits_zero_and_flags_infra_when_the_diff_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """End to end: a 403 must leave the composite step green and set the flag.

    This is the claim the fix for issue #4547 rests on. Exit 0 keeps the later
    steps running, and ``context_infra_failure=true`` is what the infra gate
    reads to skip the model invocation and write the DID_NOT_RUN verdict. If
    this regressed to exit 3, the gate would never run and the verdict file
    would never be written.
    """

    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("MAX_DIFF_LINES", "100")

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Rate limited", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "HTTP 403: API rate limit exceeded", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.main() == 0

    output = output_path.read_text(encoding="utf-8")
    assert "context_infra_failure=true" in output
    assert "context_mode=error" in output


def test_spec_file_pr_context_requires_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Spec-file PR context fails with a config error when repository is missing."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "spec-file")
    monkeypatch.setenv("CONTEXT_PATH", str(spec_path))
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert _mod.main() == 2
    assert "GITHUB_REPOSITORY is required for spec-file PR context" in capsys.readouterr().err


def test_pr_context_preserves_whitespace_body(monkeypatch: pytest.MonkeyPatch):
    """Whitespace PR bodies are preserved when gh returns them."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Title", "   \n"), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/file b/file\n+change\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert "## PR Description\n   \n\n## Changes" in context.text


def test_invalid_max_diff_lines_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Invalid action input maps to the repository config exit code."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("MAX_DIFF_LINES", "not-a-number")

    assert _mod.main() == 2
    assert "MAX_DIFF_LINES must be an integer" in capsys.readouterr().err


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


def test_write_outputs_sanitizes_context_file_identifier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """PR_NUMBER cannot introduce path separators into the context file path."""

    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("PR_NUMBER", "../evil/path")

    _mod.write_outputs(ReviewContext("hello", "full"))

    output = output_path.read_text(encoding="utf-8")
    context_file = runner_temp / "ai-review-context-previl_path.txt"
    assert context_file.read_text(encoding="utf-8") == "hello"
    assert f"context_file={context_file}" in output
    assert not (tmp_path / "evil").exists()


def test_main_returns_config_error_when_github_output_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Missing GITHUB_OUTPUT maps to the repository config exit code."""

    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    assert "::error::GITHUB_OUTPUT is required" in capsys.readouterr().err


def test_main_returns_config_error_when_runner_temp_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Missing RUNNER_TEMP does not write the context file into the repository."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    assert "::error::RUNNER_TEMP is required" in capsys.readouterr().err


def test_main_reports_output_io_separately_from_gh_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Output write failures are not reported as gh launch failures."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "missing" / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    stderr = capsys.readouterr().err
    assert "Failed to read or write context files" in stderr
    assert "Failed to run gh" not in stderr


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


GRAPHQL_QUOTA_ERROR = "GraphQL: API rate limit already exceeded for user ID 6811113."


def test_pr_metadata_uses_one_rest_call(monkeypatch: pytest.MonkeyPatch):
    """Number, title, and body come from a single REST response (issue #4333)."""

    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult(_pulls_payload(4323, "Title", "Body"), "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    metadata = _mod.fetch_pr_metadata("4323", "rjmurillo/ai-agents")

    assert metadata == _mod.PrMetadata("4323", "Title", "Body", "")
    assert calls == [["api", "repos/rjmurillo/ai-agents/pulls/4323"]]


def test_pr_metadata_falls_back_to_gh_pr_view_when_rest_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """A REST-only outage still yields context through gh pr view."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult("", "HTTP 503: Service unavailable", 1)
        return CommandResult(_pulls_payload(7, "Title", "Body"), "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.fetch_pr_metadata("7", "owner/repo").number == "7"


def test_graphql_quota_does_not_break_pr_context(monkeypatch: pytest.MonkeyPatch):
    """REST serves the context while the GraphQL bucket is drained (issue #4333)."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(4323, "Title", "Body"), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/f b/f\n+x\n", "", 0)
        raise AssertionError(f"unexpected GraphQL call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is False
    assert context.mode == "full"


def test_both_transports_failing_still_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """REQ-008-05: DID_NOT_RUN survives when REST and GraphQL both fail."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", GRAPHQL_QUOTA_ERROR, 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "API rate limit already exceeded" in context.text
    assert "first-time contributor" not in context.text


def test_permission_failure_still_names_fork_permissions(
    monkeypatch: pytest.MonkeyPatch,
):
    """The fork hint survives for the failure it actually describes."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", "HTTP 404: Not Found", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "first-time contributor" in context.text


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 403: API rate limit exceeded for user ID 6811113",
        "HTTP 403: You have exceeded a secondary rate limit",
        "HTTP 403: You have triggered an abuse detection mechanism",
    ],
)
def test_rate_limited_403_is_not_reported_as_a_permission_problem(
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
):
    """A rate-limit 403 must not be blamed on token permissions.

    FORK_PERMISSION_SIGNAL matches the bare `HTTP 403` status, so every
    REST-transport rate-limit refusal used to collect the fork hint. That is the
    #4333 misdiagnosis arriving through a transport it was never fixed for.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", stderr, 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4575", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert stderr in context.text
    assert "first-time contributor" not in context.text


def test_fork_hint_survives_when_no_rate_limit_wording_is_present():
    """Negative control: the suppression is specific, not a blanket disable.

    Without this, deleting the hint outright would still pass the test above
    while silently dropping a real diagnostic.
    """
    real_fork_failure = "HTTP 403: Resource not accessible by integration"

    assert _mod.FORK_PERMISSION_SIGNAL.search(real_fork_failure)
    assert not _mod.RATE_LIMIT_SIGNAL.search(real_fork_failure)

    context = _mod._pr_fetch_failure_context("4575", real_fork_failure)

    assert "first-time contributor" in context.text


def test_graphql_rate_limit_never_matched_the_permission_signal():
    """Edge: the GraphQL form carries no HTTP status, so it never matched.

    Records why dropping the unconditional hint sufficed for GraphQL, and why
    the REST form needed the second condition.
    """
    graphql_failure = "GraphQL: API rate limit already exceeded for user ID 6811113."

    assert not _mod.FORK_PERMISSION_SIGNAL.search(graphql_failure)
    assert _mod.RATE_LIMIT_SIGNAL.search(graphql_failure)

    context = _mod._pr_fetch_failure_context("4575", graphql_failure)

    assert "first-time contributor" not in context.text


def test_name_only_falls_back_to_rest_file_list(monkeypatch: pytest.MonkeyPatch):
    """gh pr diff --name-only is GraphQL; REST pagination backs it up."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", GRAPHQL_QUOTA_ERROR, 1)
        if arguments[:1] == ["api"]:
            if "page=1" in arguments[1]:
                return CommandResult("src/a.py\nsrc/b.py\n", "", 0)
            return CommandResult("", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.get_pr_name_only("7", "owner/repo") == "src/a.py\nsrc/b.py"


def test_unusable_rest_payload_is_not_treated_as_success(
    monkeypatch: pytest.MonkeyPatch,
):
    """A 200 with an unparseable body must not become a silent 'Unknown PR'."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("<html>Unicorn!</html>", "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    metadata = _mod.fetch_pr_metadata("7", "owner/repo")

    assert metadata.error != ""
    assert metadata.number == ""
