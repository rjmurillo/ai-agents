from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[3]
    / ".claude"
    / "skills"
    / "github-url-intercept"
    / "scripts"
    / "test_url_routing.py"
)

spec = importlib.util.spec_from_file_location("github_url_routing", SCRIPT)
assert spec is not None
assert spec.loader is not None
github_url_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github_url_routing)


def run_cli(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--url", url],
        capture_output=True,
        text=True,
        check=False,
    )


def test_gist_url_routes_to_gist_api() -> None:
    parsed = github_url_routing.parse_github_url(
        "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66"
    )

    assert parsed == {
        "owner": "rjmurillo",
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
    ],
)
def test_cli_rejects_invalid_or_unsafe_gist_url(url: str) -> None:
    result = run_cli(url)

    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert output["parsed_url"] is None
    assert output["recommended_route"] is None


def test_cli_returns_structured_success_for_gist() -> None:
    result = run_cli(
        "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66"
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["success"] is True
    assert output["recommended_route"]["command"] == (
        'gh api "gists/df38029ed77a71c6ac97cb1bc0823d66"'
    )
