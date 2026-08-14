from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

CANONICAL_SCRIPT = (
    Path(__file__).parents[3]
    / ".claude"
    / "skills"
    / "github-url-intercept"
    / "scripts"
    / "test_url_routing.py"
)
COPILOT_SCRIPT = (
    Path(__file__).parents[3]
    / "src"
    / "copilot-cli"
    / "skills"
    / "github-url-intercept"
    / "scripts"
    / "test_url_routing.py"
)
SCRIPTS = [CANONICAL_SCRIPT, COPILOT_SCRIPT]

spec = importlib.util.spec_from_file_location("github_url_routing", CANONICAL_SCRIPT)
assert spec is not None
assert spec.loader is not None
github_url_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github_url_routing)


def run_cli(script: Path, url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--url", url],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("url", "owner"),
    [
        ("https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66", "rjmurillo"),
        ("https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66", None),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66/revisions",
            "rjmurillo",
        ),
        (
            "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66/revisions",
            None,
        ),
        (
            "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66/raw/abcdef/notes.md",
            None,
        ),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66?file=notes.md",
            "rjmurillo",
        ),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66#file-notes-md",
            "rjmurillo",
        ),
    ],
)
def test_gist_url_routes_to_gist_api(url: str, owner: str | None) -> None:
    parsed = github_url_routing.parse_github_url(url)

    assert parsed == {
        "owner": owner,
        "repo": None,
        "url_type": "Gist",
        "resource_id": "df38029ed77a71c6ac97cb1bc0823d66",
        "ref": None,
        "path": None,
        "fragment_type": None,
        "fragment_id": None,
    }
    assert github_url_routing.get_recommended_route(parsed)["command"] == (
        'gh api "gists/df38029ed77a71c6ac97cb1bc0823d66"'
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gist.github.com/rjmurillo;whoami/df38029ed77a71c6ac97cb1bc0823d66",
        "https://gist.github.com/rjmurillo/abc;whoami",
        "https://gist.github.com/rjmurillo/not-a-gist-id",
        "https://gist.github.com/rjmurillo%0A/df38029ed77a71c6ac97cb1bc0823d66",
        "https://gist.github.com/rjmurillo/dead\nbeef",
        "https://gist.github.com/rjmurillo/dead\tbeef",
        "https://[github.com/rjmurillo/deadbeef",
    ],
)
@pytest.mark.parametrize("script", SCRIPTS, ids=["canonical", "copilot"])
def test_cli_rejects_invalid_or_unsafe_gist_url(script: Path, url: str) -> None:
    result = run_cli(script, url)

    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert output["parsed_url"] is None
    assert output["recommended_route"] is None


@pytest.mark.parametrize("script", SCRIPTS, ids=["canonical", "copilot"])
def test_cli_returns_structured_success_for_gist(script: Path) -> None:
    result = run_cli(
        script,
        "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66"
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["success"] is True
    assert output["recommended_route"]["command"] == (
        'gh api "gists/df38029ed77a71c6ac97cb1bc0823d66"'
    )


@pytest.mark.parametrize(
    ("url", "expected_command"),
    [
        (
            "https://github.com/owner/repo/pull/123",
            'python3 ".claude/skills/github/scripts/pr/get_pr_context.py" '
            '--pull-request "123" --owner "owner" --repo "repo"',
        ),
        (
            "https://github.com/owner/repo/issues/456",
            'python3 ".claude/skills/github/scripts/issue/get_issue_context.py" '
            '--issue "456" --owner "owner" --repo "repo"',
        ),
        (
            "https://github.com/owner/repo/blob/main/file.py",
            'gh api "repos/owner/repo/contents/file.py?ref=main"',
        ),
        (
            "https://github.com/owner/repo/tree/main/src",
            'gh api "repos/owner/repo/contents/src?ref=main"',
        ),
        (
            "https://github.com/owner/repo/commit/abcdef",
            'gh api "repos/owner/repo/commits/abcdef"',
        ),
        (
            "https://github.com/owner/repo/compare/main...feat",
            'gh api "repos/owner/repo/compare/main...feat"',
        ),
        (
            "https://github.com/owner/repo/pull/123#discussion_r456",
            'gh api "repos/owner/repo/pulls/comments/456"',
        ),
        (
            "https://github.com/owner/repo/issues/123#issuecomment-456",
            'gh api "repos/owner/repo/issues/comments/456"',
        ),
    ],
)
def test_existing_github_routes_remain_unchanged(url: str, expected_command: str) -> None:
    parsed = github_url_routing.parse_github_url(url)

    assert parsed is not None
    assert github_url_routing.get_recommended_route(parsed)["command"] == expected_command
