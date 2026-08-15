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

spec = importlib.util.spec_from_file_location("repository_url_routing", CANONICAL_SCRIPT)
assert spec is not None
assert spec.loader is not None
repository_url_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository_url_routing)


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
def test_existing_github_routes_remain_unchanged(
    url: str,
    expected_command: str,
) -> None:
    parsed = repository_url_routing.parse_github_url(url)

    assert parsed is not None
    assert repository_url_routing.get_recommended_route(parsed)["command"] == expected_command


@pytest.mark.parametrize(
    ("value", "pattern", "allow_empty", "allow_triple_dot", "expected"),
    [
        ("owner", repository_url_routing.SAFE_OWNER_REPO_RE, False, False, True),
        ("owner\n", repository_url_routing.SAFE_OWNER_REPO_RE, False, False, False),
        ("", repository_url_routing.SAFE_PATH_RE, True, False, True),
        (".claude/settings.json", repository_url_routing.SAFE_PATH_RE, False, False, True),
        ("../file", repository_url_routing.SAFE_PATH_RE, False, False, False),
        ("main...feat", repository_url_routing.SAFE_REF_RE, False, True, True),
        ("owner;whoami", repository_url_routing.SAFE_REF_RE, False, False, False),
        ("main..feat", repository_url_routing.SAFE_REF_RE, False, True, False),
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
        repository_url_routing.is_safe_input(
            value,
            pattern,
            allow_empty=allow_empty,
            allow_triple_dot=allow_triple_dot,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (".claude/settings.json", True),
        ("%2e%2e/settings.json", False),
        (".%2e/settings.json", False),
        ("..%2fsettings.json", False),
        ("file..name.txt", True),
    ],
)
def test_safe_path_traversal_segments(
    value: str,
    expected: bool,
) -> None:
    assert (
        repository_url_routing.is_safe_input(
            value,
            repository_url_routing.SAFE_PATH_RE,
            reject_path_traversal=True,
        )
        is expected
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/owner/repo/pull/1",
        "https://github.com/owner\n/repo/pull/1",
        "https://github.com/owner/repo\n/pull/1",
        "https://github.com/owner/repo/blob/../file.py",
        "https://github.com/owner/repo/blob/main/src/../file.py",
        "https://github.com/owner/repo/blob/main/.%2e/file.py",
        "https://github.com/owner/repo/blob/main/%2e%2e/file.py",
        "https://github.com/owner/repo/tree/../src",
        "https://github.com/owner/repo/tree/main/src/../file.py",
        "https://github.com/owner/repo/compare/main..feat",
    ],
)
def test_existing_github_parser_rejects_unsafe_urls(url: str) -> None:
    assert repository_url_routing.parse_github_url(url) is None


def test_tree_route_allows_empty_path() -> None:
    parsed = repository_url_routing.parse_github_url(
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

    assert repository_url_routing.get_recommended_route(parsed)["command"] == "unknown"


def test_main_returns_structured_success(capsys: pytest.CaptureFixture[str]) -> None:
    result = repository_url_routing.main(
        ["--url", "https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439"]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_main_returns_structured_dotfile_blob(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = repository_url_routing.main(
        ["--url", "https://github.com/owner/repo/blob/main/.claude/settings.json"]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["parsed_url"]["path"] == ".claude/settings.json"
    assert output["recommended_route"]["command"] == (
        'gh api "repos/owner/repo/contents/.claude/settings.json?ref=main"'
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/repo/blob/main/.%2e/file.py",
        "https://github.com/owner/repo/blob/main/%2e%2e/file.py",
    ],
)
def test_main_rejects_encoded_path_traversal(
    capsys: pytest.CaptureFixture[str],
    url: str,
) -> None:
    result = repository_url_routing.main(["--url", url])

    assert result == 1
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is False
    assert output["parsed_url"] is None
    assert output["recommended_route"] is None


def test_main_returns_structured_invalid_url(capsys: pytest.CaptureFixture[str]) -> None:
    result = repository_url_routing.main(["--url", "https://gist.github.com/invalid"])

    assert result == 1
    assert json.loads(capsys.readouterr().out)["parsed_url"] is None


def test_main_returns_structured_unknown_route(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = repository_url_routing.main(
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


@pytest.mark.parametrize("script", [CANONICAL_SCRIPT, COPILOT_SCRIPT])
def test_script_supports_clean_process_path_import(script: Path) -> None:
    code = (
        "import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('route', {str(script)!r}); "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
