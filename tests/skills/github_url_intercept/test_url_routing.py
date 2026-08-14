from __future__ import annotations

import importlib.util
import json
import re
import runpy
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
    ("url", "owner", "gist_id"),
    [
        ("https://gist.github.com/schacon/1", "schacon", "1"),
        (
            "https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439",
            "PurpleBooth",
            "6f1ba788bf70fb501439",
        ),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66",
            "rjmurillo",
            "df38029ed77a71c6ac97cb1bc0823d66",
        ),
        (
            "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66",
            None,
            "df38029ed77a71c6ac97cb1bc0823d66",
        ),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66/revisions",
            "rjmurillo",
            "df38029ed77a71c6ac97cb1bc0823d66",
        ),
        (
            "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66/revisions",
            None,
            "df38029ed77a71c6ac97cb1bc0823d66",
        ),
        (
            "https://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66.js",
            "rjmurillo",
            "df38029ed77a71c6ac97cb1bc0823d66",
        ),
    ],
)
def test_gist_url_routes_to_gist_api(
    url: str,
    owner: str | None,
    gist_id: str,
) -> None:
    parsed = github_url_routing.parse_github_url(url)

    assert parsed == {
        "owner": owner,
        "repo": None,
        "url_type": "Gist",
        "resource_id": gist_id,
        "raw_url": None,
        "revision": None,
        "requested_file": None,
        "requested_file_slug": None,
        "requested_file_base_slug": None,
        "ref": None,
        "path": None,
        "fragment_type": None,
        "fragment_id": None,
    }
    assert github_url_routing.get_recommended_route(parsed)["command"] == (
        f'gh api "gists/{gist_id}"'
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gist.github.com/rjmurillo;whoami/df38029ed77a71c6ac97cb1bc0823d66",
        "https://gist.github.com/rjmurillo/abc;whoami",
        "https://gist.github.com/rjmurillo/not-a-gist-id",
        "https://gist.github.com/rjmurillo/dead#beef",
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
    ("url", "revision", "requested_file", "expected_command"),
    [
        (
            "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66/"
            "a1b2c3d4e5f678901234567890abcdef12345678",
            "a1b2c3d4e5f678901234567890abcdef12345678",
            None,
            'gh api "gists/df38029ed77a71c6ac97cb1bc0823d66/'
            'a1b2c3d4e5f678901234567890abcdef12345678"',
        ),
        (
            "https://gist.githubusercontent.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66/raw/"
            "a1b2c3d4e5f678901234567890abcdef12345678/notes.md",
            None,
            None,
            "gh api https://gist.githubusercontent.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66/raw/"
            "a1b2c3d4e5f678901234567890abcdef12345678/notes.md",
        ),
        (
            "https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66/raw/notes.md",
            None,
            None,
            "gh api https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66/raw/notes.md",
        ),
        (
            "https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439/raw",
            None,
            None,
            "gh api https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439/raw",
        ),
    ],
)
def test_gist_route_preserves_revision_and_file_selector(
    url: str,
    revision: str | None,
    requested_file: str | None,
    expected_command: str,
) -> None:
    parsed = github_url_routing.parse_github_url(url)

    assert parsed is not None
    assert parsed["revision"] == revision
    assert parsed["requested_file"] == requested_file
    assert github_url_routing.get_recommended_route(parsed)["command"] == expected_command


@pytest.mark.parametrize(
    ("url", "expected_file", "expected_slug", "expected_base_slug"),
    [
        (
            "https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66.js?file=debug%20log.txt",
            "debug log.txt",
            None,
            None,
        ),
        (
            "https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66#file-debug-log-txt",
            None,
            "debug-log-txt",
            "debug-log-txt",
        ),
        (
            "https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66#file-hs_err_pid37480-log-L12-L18",
            None,
            "hs_err_pid37480-log-L12-L18",
            "hs_err_pid37480-log",
        ),
        (
            "https://gist.github.com/rjmurillo/"
            "df38029ed77a71c6ac97cb1bc0823d66#file-prettierrc-json",
            None,
            "prettierrc-json",
            "prettierrc-json",
        ),
    ],
)
def test_gist_route_preserves_page_file_selector(
    url: str,
    expected_file: str | None,
    expected_slug: str | None,
    expected_base_slug: str | None,
) -> None:
    parsed = github_url_routing.parse_github_url(url)

    assert parsed is not None
    assert parsed["requested_file"] == expected_file
    assert parsed["requested_file_slug"] == expected_slug
    assert parsed["requested_file_base_slug"] == expected_base_slug
    command = github_url_routing.get_recommended_route(parsed)["command"]
    assert "--jq" in command
    if expected_base_slug and expected_base_slug != expected_slug:
        assert expected_slug not in command


def test_normal_gist_query_does_not_hide_sibling_files() -> None:
    parsed = github_url_routing.parse_github_url(
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66?file=debug.log"
    )

    assert parsed is not None
    assert parsed["requested_file"] is None
    assert "--jq" not in github_url_routing.get_recommended_route(parsed)["command"]


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
            "https://github.com/owner/repo/pull/123#pullrequestreview-456",
            'gh api "repos/owner/repo/pulls/123/reviews/456"',
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


@pytest.mark.parametrize(
    ("value", "pattern", "allow_empty", "allow_triple_dot", "expected"),
    [
        ("owner", github_url_routing.SAFE_OWNER_REPO_RE, False, False, True),
        ("owner\n", github_url_routing.SAFE_OWNER_REPO_RE, False, False, False),
        ("", github_url_routing.SAFE_PATH_RE, True, False, True),
        ("../file", github_url_routing.SAFE_PATH_RE, False, False, False),
        ("main...feat", github_url_routing.SAFE_REF_RE, False, True, True),
    ],
)
def test_safe_input_contract(
    value: str,
    pattern: re.Pattern[str],
    allow_empty: bool,
    allow_triple_dot: bool,
    expected: bool,
) -> None:
    assert (
        github_url_routing.is_safe_input(
            value,
            pattern,
            allow_empty=allow_empty,
            allow_triple_dot=allow_triple_dot,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("value", "allow_triple_dot"),
    [
        ("owner;whoami", False),
        ("main..feat", True),
    ],
)
def test_safe_input_rejects_dangerous_or_traversal_values(
    value: str,
    allow_triple_dot: bool,
) -> None:
    assert not github_url_routing.is_safe_input(
        value,
        github_url_routing.SAFE_REF_RE,
        allow_triple_dot=allow_triple_dot,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gist.github.com/rjmurillo/dead\nbeef",
        "https://[github.com/rjmurillo/deadbeef",
        "ftp://gist.github.com/rjmurillo/df38029ed77a71c6ac97cb1bc0823d66",
        "https://gist.github.com",
        "https://gist.githubusercontent.com/df38029ed77a71c6ac97cb1bc0823d66",
        "https://gist.githubusercontent.com/owner;whoami/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/file.txt",
        "https://gist.githubusercontent.com/owner/deadbeef/raw/file.txt",
        "https://gist.githubusercontent.com/owner/"
        "df38029ed77a71c6ac97cb1bc0823d66/file.txt",
        "https://gist.github.com/df38029ed77a71c6ac97cb1bc0823d66/raw/file.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/benign/../malicious.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/%7Bowner%7D/file.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/file%0Aname.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/dir%2Ffile.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/file.txt?file=other.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/file.txt#file-other-txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66.js?file=safe.txt&file=evil.txt",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66.js?file=",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/unknown",
        "https://gist.github.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/"
        "a1b2c3d4e5f678901234567890abcdef12345678/extra",
    ],
)
def test_gist_parser_rejects_incomplete_or_unsupported_urls(url: str) -> None:
    assert github_url_routing.parse_gist_url(url) is None


def test_raw_http_url_is_normalized_to_https() -> None:
    url = (
        "http://gist.githubusercontent.com/rjmurillo/"
        "df38029ed77a71c6ac97cb1bc0823d66/raw/notes.md"
    )
    parsed = github_url_routing.parse_github_url(url)

    assert parsed is not None
    assert parsed["raw_url"].startswith("https://")
    assert "--jq" not in github_url_routing.get_recommended_route(parsed)["command"]


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/owner/repo/pull/1",
        "https://github.com/owner\n/repo/pull/1",
        "https://github.com/owner/repo\n/pull/1",
        "https://github.com/owner/repo/blob/../file.py",
        "https://github.com/owner/repo/blob/main/src/../file.py",
        "https://github.com/owner/repo/tree/../src",
        "https://github.com/owner/repo/tree/main/src/../file.py",
        "https://github.com/owner/repo/compare/main..feat",
    ],
)
def test_existing_github_parser_rejects_unsafe_urls(url: str) -> None:
    assert github_url_routing.parse_github_url(url) is None


def test_tree_route_allows_empty_path() -> None:
    parsed = github_url_routing.parse_github_url(
        "https://github.com/owner/repo/tree/main/"
    )

    assert parsed is not None
    assert parsed["path"] == ""


def test_unknown_fragment_route_returns_unknown_command() -> None:
    parsed = {
        "owner": "owner",
        "repo": "repo",
        "url_type": "Pull",
        "resource_id": "1",
        "ref": None,
        "path": None,
        "fragment_type": "unsupported",
        "fragment_id": "2",
    }

    assert github_url_routing.get_recommended_route(parsed)["command"] == "unknown"


def test_main_returns_structured_success(capsys: pytest.CaptureFixture[str]) -> None:
    result = github_url_routing.main(
        ["--url", "https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439"]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_main_returns_structured_invalid_url(capsys: pytest.CaptureFixture[str]) -> None:
    result = github_url_routing.main(["--url", "https://gist.github.com/invalid"])

    assert result == 1
    assert json.loads(capsys.readouterr().out)["parsed_url"] is None


def test_main_returns_structured_unknown_route(capsys: pytest.CaptureFixture[str]) -> None:
    result = github_url_routing.main(
        ["--url", "https://github.com/owner/repo/discussions/1"]
    )

    assert result == 1
    output = json.loads(capsys.readouterr().out)
    assert output["parsed_url"]["url_type"] == "Unknown"
    assert output["recommended_route"] is None


def test_module_entrypoint_exits_with_main_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(CANONICAL_SCRIPT),
            "--url",
            "https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439",
        ],
    )

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(CANONICAL_SCRIPT), run_name="__main__")

    assert error.value.code == 0


def test_canonical_and_copilot_scripts_are_identical() -> None:
    assert CANONICAL_SCRIPT.read_bytes() == COPILOT_SCRIPT.read_bytes()
