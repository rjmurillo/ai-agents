"""CLI tests for github-url-intercept routing."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "github-url-intercept"
    / "scripts"
    / "test_url_routing.py"
)
PLUGIN_ROOT_EXPR = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"


def _load_module():
    spec = importlib.util.spec_from_file_location("github_url_routing", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(url: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    module = _load_module()
    rc = module.main(["--url", url])
    captured = capsys.readouterr().out
    return rc, json.loads(captured)


@pytest.mark.parametrize(
    ("url", "method", "command"),
    [
        (
            "https://github.com/rjmurillo/ai-agents/pull/123",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/pr/get_pr_context.py" '
            '--pull-request "123" --owner "rjmurillo" --repo "ai-agents"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/checks",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/pr/get_pr_checks.py" '
            '--pull-request "123" --owner "rjmurillo" --repo "ai-agents"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/files",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/pr/get_pr_context.py" '
            '--pull-request "123" --owner "rjmurillo" --repo "ai-agents" '
            "--include-changed-files",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/changes",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/pr/get_pr_context.py" '
            '--pull-request "123" --owner "rjmurillo" --repo "ai-agents" --include-diff',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/commits",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/pr/get_pr_context.py" '
            '--pull-request "123" --owner "rjmurillo" --repo "ai-agents"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/issues/456",
            "Script",
            f'python3 "{PLUGIN_ROOT_EXPR}/skills/github/scripts/issue/get_issue_context.py" '
            '--issue "456" --owner "rjmurillo" --repo "ai-agents"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/discussions/789",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/discussions/789"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/actions/runs/123",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/actions/runs/123"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/actions/runs/123/job/456",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/actions/jobs/456"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/commit/abc1234",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/commits/abc1234"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/compare/main...feature",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/compare/main...feature"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/blob/main/src/app.py",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/contents/src/app.py?ref=main"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/tree/main/src",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/contents/src?ref=main"',
        ),
    ],
)
def test_routing_success(
    capsys: pytest.CaptureFixture[str],
    url: str,
    method: str,
    command: str,
) -> None:
    module = _load_module()
    rc = module.main(["--url", url])
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["success"] is True
    assert output["recommended_route"]["method"] == method
    assert output["recommended_route"]["command"] == command


@pytest.mark.parametrize(
    ("url", "method", "command"),
    [
        (
            "https://github.com/rjmurillo/ai-agents/pull/123#pullrequestreview-456789",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/pulls/123/reviews/456789"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/files#r456",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/pulls/comments/456"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/changes#r456",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/pulls/comments/456"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/checks#r456",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/pulls/comments/456"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123#discussion_r987654321",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/pulls/comments/987654321"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/issues/456#issuecomment-789123456",
            "GhApi",
            'gh api "repos/rjmurillo/ai-agents/issues/comments/789123456"',
        ),
    ],
)
def test_fragment_routes_success(
    capsys: pytest.CaptureFixture[str],
    url: str,
    method: str,
    command: str,
) -> None:
    module = _load_module()
    rc = module.main(["--url", url])
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["success"] is True
    assert output["recommended_route"]["method"] == method
    assert output["recommended_route"]["command"] == command


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/rjmurillo/ai-agents/pull/123/not-a-real-view",
        "https://github.com/rjmurillo/ai-agents/issues/456/not-a-real-view",
        "https://github.com/rjmurillo/ai-agents/commit/abcxyz",
        "https://github.com/rjmurillo/ai-agents/pull/123/checks/extra",
        "https://github.com/rjmurillo/ai-agents/actions/runs/123/job/456/extra",
        "https://github.com/rjmurillo/ai-agents/pull/123#issuecomment-123456789",
        "https://github.com/rjmurillo/ai-agents/pull/123/files#issuecomment-789",
        "https://github.com/rjmurillo/ai-agents/pull/123/changes#issuecomment-789",
        "https://github.com/rjmurillo/ai-agents/issues/456#discussion_r123",
        "https://github.com/rjmurillo/ai-agents/discussions/789#issuecomment-123",
        "https://github.com/rjmurillo/ai-agents/actions/runs/123#issuecomment-123",
        "https://github.com/rjmurillo/ai-agents/blob/main/src/app.py#r123",
        "https://github.com/rjmurillo/ai-agents/tree/main/src#issuecomment-123",
        "https://github.com/rjmurillo/ai-agents/compare/main...feature#r123",
    ],
)
def test_rejects_non_exact_routes(capsys: pytest.CaptureFixture[str], url: str) -> None:
    module = _load_module()
    rc = module.main(["--url", url])
    output = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert output["success"] is False
    assert output["recommended_route"] is None
    assert "Invalid GitHub URL format" in output["error"]
