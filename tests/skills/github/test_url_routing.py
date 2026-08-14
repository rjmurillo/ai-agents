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
    ("url", "method", "command_snippet"),
    [
        (
            "https://github.com/rjmurillo/ai-agents/pull/123",
            "Script",
            'get_pr_context.py" --pull-request "123"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/checks",
            "Script",
            'get_pr_checks.py" --pull-request "123"',
        ),
        (
            "https://github.com/rjmurillo/ai-agents/pull/123/files#r456",
            "GhApi",
            "pulls/comments/456",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/issues/456#issuecomment-789",
            "GhApi",
            "issues/comments/789",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/discussions/789",
            "GhApi",
            "discussions/789",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/actions/runs/123/job/456",
            "GhApi",
            "actions/jobs/456",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/commit/abc1234",
            "GhApi",
            "commits/abc1234",
        ),
        (
            "https://github.com/rjmurillo/ai-agents/compare/main...feature",
            "GhApi",
            "compare/main...feature",
        ),
    ],
)
def test_routing_success(capsys: pytest.CaptureFixture[str], url: str, method: str, command_snippet: str) -> None:
    module = _load_module()
    rc = module.main(["--url", url])
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["success"] is True
    assert output["recommended_route"]["method"] == method
    assert command_snippet in output["recommended_route"]["command"]


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/rjmurillo/ai-agents/pull/123/not-a-real-view",
        "https://github.com/rjmurillo/ai-agents/issues/456/not-a-real-view",
        "https://github.com/rjmurillo/ai-agents/commit/abcxyz",
        "https://github.com/rjmurillo/ai-agents/pull/123/checks/extra",
        "https://github.com/rjmurillo/ai-agents/actions/runs/123/job/456/extra",
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

