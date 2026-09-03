"""Tests for GitHub Core module, porting and exceeding Pester coverage."""

from __future__ import annotations

import ast
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import (
    REPO_ROOT_GIT_FAILED,
    REPO_ROOT_NOT_A_REPO,
    REPO_ROOT_OK,
    FetchStatus,
    RateLimitResult,
    RateLimitStatus,
    RepoInfo,
    assert_gh_authenticated,
    assert_valid_body_file,
    bot_config,
    check_workflow_rate_limit,
    count_unresolved_threads,
    create_issue_comment,
    error_and_exit,
    filter_unresolved_threads,
    get_all_prs_with_comments,
    get_bot_authors,
    get_bot_authors_config,
    get_issue_comments,
    get_priority_emoji,
    get_reaction_emoji,
    get_repo_info,
    get_trusted_source_comments,
    get_unresolved_review_threads,
    gh_api_paginated,
    gh_graphql,
    is_gh_authenticated,
    is_github_name_valid,
    is_safe_file_path,
    resolve_repo_params,
    resolve_repo_root,
    safe_log_str,
    update_issue_comment,
    validation,
)
from scripts.github_core.api import (
    _403_PATTERN,
    REST_PAGE_PACE_SECONDS,
    REST_REFUSAL_BACKOFF_SECONDS,
    _retry_after_delay,
)
from scripts.github_core.bot_config import _DEFAULT_BOTS
from tests.mock_fidelity import assert_mock_keys_match

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    """Build a CompletedProcess for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _mock_run(stdout: str = "", stderr: str = "", rc: int = 0):
    """Return a side_effect function that always returns a fixed CompletedProcess."""

    def _side_effect(*args, **kwargs):
        return _completed(stdout=stdout, stderr=stderr, rc=rc)

    return _side_effect


def _thread(tid: str, resolved: bool, db_id: int) -> dict:
    """Build a minimal review thread dict for GraphQL response mocking."""
    return {
        "id": tid,
        "isResolved": resolved,
        "comments": {"nodes": [{"databaseId": db_id}]},
    }


def test_thread_mock_keys_subset_of_fixture():
    """The minimal _thread mock should be a subset of the review_thread fixture."""
    thread = _thread("T1", False, 1)
    assert_mock_keys_match(thread, "review_thread", allow_missing=True)


# ---------------------------------------------------------------------------
# Validation: is_github_name_valid
# ---------------------------------------------------------------------------


class TestIsGitHubNameValid:
    def test_valid_owner(self):
        assert is_github_name_valid("rjmurillo", "Owner") is True

    def test_valid_owner_with_hyphens(self):
        assert is_github_name_valid("my-org", "Owner") is True

    def test_owner_cannot_start_with_hyphen(self):
        assert is_github_name_valid("-badname", "Owner") is False

    def test_owner_cannot_end_with_hyphen(self):
        assert is_github_name_valid("badname-", "Owner") is False

    def test_owner_max_39_chars(self):
        assert is_github_name_valid("a" * 39, "Owner") is True
        # Pattern: start(1) + middle(0-37) + end(1) = max 39 chars
        assert is_github_name_valid("a" * 40, "Owner") is False

    def test_valid_repo(self):
        assert is_github_name_valid("ai-agents", "Repo") is True

    @pytest.mark.parametrize("name_type", ["repo", "Repo", "REPO"])
    def test_repo_name_type_is_case_insensitive(self, name_type: str):
        assert is_github_name_valid("ai-agents", name_type) is True
        assert is_github_name_valid("..", name_type) is False

    def test_repo_allows_dots(self):
        assert is_github_name_valid("my.repo.name", "Repo") is True

    def test_repo_allows_underscores(self):
        assert is_github_name_valid("my_repo", "Repo") is True

    def test_repo_max_100_chars(self):
        assert is_github_name_valid("a" * 100, "Repo") is True
        assert is_github_name_valid("a" * 101, "Repo") is False

    def test_empty_name_is_invalid(self):
        assert is_github_name_valid("", "Owner") is False
        assert is_github_name_valid("", "Repo") is False

    def test_whitespace_only_is_invalid(self):
        assert is_github_name_valid("   ", "Owner") is False

    def test_invalid_type_returns_false(self):
        assert is_github_name_valid("foo", "Invalid") is False

    @pytest.mark.parametrize("name", [".", ".."])
    @pytest.mark.parametrize("name_type", ["repo", "Repo", "REPO"])
    def test_repo_rejects_the_two_directory_aliases(self, name: str, name_type: str):
        """`.` and `..` are the only names GitHub refuses outright.

        They are also the two that carry traversal meaning once a caller
        interpolates them into a URL path, which several callers do.

        `name_type` is documented case-insensitive, so the rejection has to
        hold for every spelling a caller may pass. Testing one spelling would
        let a guard that keys off a single literal survive.
        """
        assert is_github_name_valid(name, name_type) is False

    @pytest.mark.parametrize("name", [".", ".."])
    @pytest.mark.parametrize("name_type", ["owner", "Owner", "OWNER"])
    def test_owner_rejects_the_two_directory_aliases(self, name: str, name_type: str):
        assert is_github_name_valid(name, name_type) is False

    def test_longer_dot_runs_stay_valid(self):
        """Only the two aliases are reserved. `...` is a legal repository name.

        Rejecting every all-dot name would be a wider rule than GitHub's and
        would fail a name a user can really create.
        """
        assert is_github_name_valid("...", "Repo") is True
        assert is_github_name_valid("....", "Repo") is True

    def test_dots_elsewhere_in_a_name_stay_valid(self):
        """The guard matches whole names, not substrings."""
        assert is_github_name_valid("..leading", "Repo") is True
        assert is_github_name_valid("trailing..", "Repo") is True
        assert is_github_name_valid("mid..dle", "Repo") is True


# ---------------------------------------------------------------------------
# Validation: is_safe_file_path
# ---------------------------------------------------------------------------


class TestIsSafeFilePath:
    def test_safe_path_within_base(self, tmp_path: Path):
        child = tmp_path / "child.txt"
        child.touch()
        assert is_safe_file_path(str(child), str(tmp_path)) is True

    def test_traversal_blocked(self, tmp_path: Path):
        bad_path = str(tmp_path / ".." / "escape.txt")
        assert is_safe_file_path(bad_path, str(tmp_path)) is False

    def test_default_base_is_repo_root(self, tmp_path: Path):
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(tmp_path, REPO_ROOT_OK),
        ):
            assert is_safe_file_path(str(child)) is True

    def test_default_base_falls_back_to_cwd_when_there_is_no_repository(self, tmp_path: Path):
        """Git answered. "No repository" is a fact, so cwd is a real boundary."""
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(None, REPO_ROOT_NOT_A_REPO),
        ):
            with patch("os.getcwd", return_value=str(tmp_path)):
                assert is_safe_file_path(str(child)) is True

    def test_git_failure_does_not_silently_become_a_cwd_check(self, tmp_path: Path):
        """The false accept. Git failed, so containment cannot be answered.

        Before this fix the base silently became the working directory, so a
        path nowhere near the repository passed the repository containment
        check purely because the process happened to be sitting next to it.
        """
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(None, REPO_ROOT_GIT_FAILED),
        ):
            with patch("os.getcwd", return_value=str(tmp_path)):
                assert is_safe_file_path(str(child)) is False

    def test_explicit_base_never_consults_git(self, tmp_path: Path):
        """A caller-supplied base is authoritative; git must not be run at all."""
        child = tmp_path / "file.txt"
        child.touch()
        with patch("scripts.github_core.repo.resolve_repo_root") as resolver:
            assert is_safe_file_path(str(child), str(tmp_path)) is True
        resolver.assert_not_called()

    def test_rejects_backslash_traversal(self):
        assert is_safe_file_path("foo\\..\\bar") is False

    def test_rejects_sibling_directory_prefix(self, tmp_path: Path):
        base = tmp_path / "safe"
        base.mkdir()
        sibling = tmp_path / "safe_evil"
        sibling.mkdir()
        evil_file = sibling / "secret.txt"
        evil_file.touch()
        assert is_safe_file_path(str(evil_file), str(base)) is False

    def test_allows_exact_base_path(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        target.touch()
        assert is_safe_file_path(str(target), str(target)) is True


# ---------------------------------------------------------------------------
# Validation: assert_valid_body_file
# ---------------------------------------------------------------------------


class TestAssertValidBodyFile:
    def test_raises_when_file_missing(self):
        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file("/nonexistent/path/file.txt")
        assert exc.value.code == 2

    def test_passes_when_file_exists(self, tmp_path: Path):
        f = tmp_path / "body.md"
        f.write_text("hello")
        assert_valid_body_file(str(f), str(tmp_path))

    def test_raises_on_traversal(self, tmp_path: Path):
        # Create file at parent so it exists, but path has traversal
        parent = tmp_path.parent
        f = parent / "body.md"
        f.write_text("hello")
        try:
            traversal_path = str(tmp_path / ".." / "body.md")
            with pytest.raises(SystemExit) as exc:
                assert_valid_body_file(traversal_path, str(tmp_path))
            assert exc.value.code == 2
        finally:
            f.unlink(missing_ok=True)

    def test_accepts_tmpdir_file_when_base_is_none(self, tmp_path: Path, monkeypatch):
        """File under TMPDIR accepted when allowed_base is None (mktemp staging)."""
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        body = tmp_path / "pr-reply.md"
        body.write_text("draft")
        assert_valid_body_file(str(body), None)

    def test_accepts_system_tempfile_when_base_is_none(self, monkeypatch):
        """File under tempfile.gettempdir() accepted when allowed_base is None."""
        import tempfile

        monkeypatch.delenv("TMPDIR", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("draft")
            tmp_file = f.name
        try:
            assert_valid_body_file(tmp_file, None)
        finally:
            Path(tmp_file).unlink(missing_ok=True)

    def test_rejects_file_outside_repo_and_all_tempdirs(self, external_tmp_path: Path, monkeypatch):
        """File outside both repo and every candidate temp root is rejected."""
        outside_dir = external_tmp_path / "not-a-temp-dir"
        outside_dir.mkdir()
        outside_file = outside_dir / "body.md"
        outside_file.write_text("hello")

        unrelated_tmp = external_tmp_path / "unrelated-tmp"
        unrelated_tmp.mkdir()
        monkeypatch.setenv("TMPDIR", str(unrelated_tmp))

        from scripts.github_core import validation as _validation

        monkeypatch.setattr(
            _validation,
            "_candidate_temp_roots",
            lambda: [str(unrelated_tmp.resolve())],
        )

        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file(str(outside_file), None)
        assert exc.value.code == 2


class TestCandidateGitDirRoots:
    """Tests for _candidate_git_dir_roots: git-dir scratch path discovery."""

    def test_returns_git_dir_when_in_repo(self):
        """Returns the resolved git dir when run inside a git repository."""
        from scripts.github_core.validation import _candidate_git_dir_roots

        roots = _candidate_git_dir_roots()
        assert isinstance(roots, list)
        # We are inside a git repository, so at least one root must be returned.
        assert len(roots) >= 1
        from pathlib import Path

        assert all(Path(r).is_dir() for r in roots)

    def test_returns_empty_list_when_git_fails(self, monkeypatch):
        """Returns [] when git exits non-zero (not in a repo)."""
        import subprocess

        from scripts.github_core.validation import _candidate_git_dir_roots

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _candidate_git_dir_roots() == []

    def test_returns_empty_list_on_timeout(self, monkeypatch):
        """Returns [] when git subprocess times out."""
        import subprocess

        from scripts.github_core.validation import _candidate_git_dir_roots

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["git"], timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _candidate_git_dir_roots() == []


class TestAssertValidBodyFileGitDir:
    """assert_valid_body_file accepts files stored under the git dir (issue #4276)."""

    def test_accepts_file_under_git_dir(self, monkeypatch):
        """Body file under the worktree git dir is accepted when allowed_base is None."""
        # Create a real temp dir that acts as the fake git dir.
        import tempfile
        from pathlib import Path

        from scripts.github_core import validation as _validation

        with tempfile.TemporaryDirectory() as fake_git_dir:
            body = Path(fake_git_dir) / "reply.md"
            body.write_text("draft reply")

            monkeypatch.setattr(
                _validation,
                "_candidate_git_dir_roots",
                lambda: [str(Path(fake_git_dir).resolve())],
            )
            # Override repo-root check to not accept this path.
            monkeypatch.setattr(
                _validation,
                "_candidate_temp_roots",
                lambda: [],
            )

            monkeypatch.setattr(
                _validation,
                "is_safe_file_path",
                lambda path, base=None: (
                    base is not None and str(Path(path).resolve()).startswith(
                        str(Path(base).resolve())
                    )
                ),
            )
            # This must not raise SystemExit.
            _validation.assert_valid_body_file(str(body), None)

    def test_still_rejects_file_outside_all_allowed_roots(
        self, external_tmp_path: Path, monkeypatch
    ):
        """File outside repo, temp dirs, and git dir is still rejected."""
        from scripts.github_core import validation as _validation

        outside_dir = external_tmp_path / "not-allowed"
        outside_dir.mkdir()
        outside_file = outside_dir / "body.md"
        outside_file.write_text("hello")

        monkeypatch.setattr(_validation, "_candidate_temp_roots", lambda: [])
        monkeypatch.setattr(_validation, "_candidate_git_dir_roots", lambda: [])

        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file(str(outside_file), None)
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorAndExit:
    def test_raises_system_exit_with_code(self):
        with pytest.raises(SystemExit) as exc:
            error_and_exit("boom", 3)
        assert exc.value.code == 3

    def test_writes_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            error_and_exit("error message", 1)
        assert "error message" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestGetRepoInfo:
    def test_parses_https_remote(self):
        stdout = "https://github.com/rjmurillo/ai-agents.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="rjmurillo", repo="ai-agents")

    @pytest.mark.parametrize(
        "stdout, expected_repo",
        [
            ("https://github.com/rjmurillo/moq.analyzers.git\n", "moq.analyzers"),
            ("git@github.com:rjmurillo/repo.with.dots.git\n", "repo.with.dots"),
            ("https://github.com/rjmurillo/repo.with.dots\n", "repo.with.dots"),
            ("https://alice@github.com/rjmurillo/moq.analyzers.git\n", "moq.analyzers"),
            ("git+ssh://git@github.com/rjmurillo/repo.with.dots.git\n", "repo.with.dots"),
        ],
    )
    def test_preserves_dots_in_repository_name(self, stdout, expected_repo):
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="rjmurillo", repo=expected_repo)

    def test_parses_ssh_remote(self):
        stdout = "git@github.com:myorg/myrepo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="myorg", repo="myrepo")

    @pytest.mark.parametrize(
        "stdout",
        [
            "https://gitlab.com/rjmurillo/moq.analyzers.git\n",
            "https://notgithub.com/rjmurillo/moq.analyzers.git\n",
            "https://evil.example/github.com/rjmurillo/moq.analyzers.git\n",
        ],
    )
    def test_returns_none_for_non_github_remote(self, stdout):
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() is None

    def test_returns_none_when_not_git_repo(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fatal")):
            assert get_repo_info() is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
            assert get_repo_info() is None

    def test_strips_dot_git_suffix(self):
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info is not None
        assert info.repo == "repo"

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert get_repo_info() is None

    def test_returns_repo_info_type(self):
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert isinstance(info, RepoInfo)


class TestResolveRepoParams:
    def test_uses_provided_params(self):
        result = resolve_repo_params("myowner", "myrepo")
        assert result == RepoInfo(owner="myowner", repo="myrepo")

    def test_infers_from_git_remote(self):
        with patch(
            "scripts.github_core.api.get_repo_info",
            return_value=RepoInfo(owner="inferred", repo="repo"),
        ):
            result = resolve_repo_params()
        assert result == RepoInfo(owner="inferred", repo="repo")

    def test_exits_when_cannot_infer(self):
        with patch("scripts.github_core.api.get_repo_info", return_value=None):
            with pytest.raises(SystemExit) as exc:
                resolve_repo_params()
            assert exc.value.code == 2

    def test_exits_on_invalid_owner(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("-bad", "repo")
        assert exc.value.code == 2

    def test_exits_on_invalid_repo(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("owner", "bad/repo/name!")
        assert exc.value.code == 2

    def test_returns_repo_info_type(self):
        result = resolve_repo_params("owner", "repo")
        assert isinstance(result, RepoInfo)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestIsGhAuthenticated:
    def test_true_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert is_gh_authenticated() is True

    def test_false_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert is_gh_authenticated() is False

    def test_false_when_gh_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_gh_authenticated() is False

    def test_false_when_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=10)):
            assert is_gh_authenticated() is False

    def test_returns_bool(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert isinstance(is_gh_authenticated(), bool)


class TestAssertGhAuthenticated:
    def test_passes_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert_gh_authenticated()

    def test_exits_4_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
            assert exc.value.code == 4


# ---------------------------------------------------------------------------
# API: gh_api_paginated
# ---------------------------------------------------------------------------


class TestGhApiPaginated:
    def test_single_page(self):
        items = [{"id": 1}, {"id": 2}]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(items))):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == items

    def test_multi_page(self):
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": 100}]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            data = page1 if call_count == 1 else page2
            return _completed(stdout=json.dumps(data))

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "scripts.github_core.api.time.sleep"
        ) as sleep:
            result = gh_api_paginated("repos/o/r/issues", page_size=100)
        assert len(result) == 101
        sleep.assert_called_once_with(REST_PAGE_PACE_SECONDS)

    def test_rate_limit_refusal_retries_page_before_success(self):
        items = [{"id": 1}]
        calls: list[list[str]] = []
        sleeps: list[float] = []

        def _side_effect(command, **kwargs):
            del kwargs
            calls.append(command)
            if len(calls) == 1:
                return _completed(
                    rc=1,
                    stderr="HTTP 403: API rate limit exceeded for user ID 6811113",
                )
            return _completed(stdout=json.dumps(items))

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "scripts.github_core.api.time.sleep", sleeps.append
        ), pytest.warns(UserWarning, match="GitHub REST page request refused"):
            result = gh_api_paginated("repos/o/r/issues")

        assert result == items
        assert len(calls) == 2
        assert sleeps == [REST_REFUSAL_BACKOFF_SECONDS[0]]

    def test_empty_response(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == []

    def test_first_page_failure_exits(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="error")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_mid_pagination_failure_returns_partial(self):
        page1 = [{"id": i} for i in range(100)]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(rc=1, stderr="rate limited")

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "scripts.github_core.api.time.sleep"
        ):
            with pytest.warns(UserWarning, match="Returning partial results"):
                result = gh_api_paginated("repos/o/r/issues")
        assert len(result) == 100

    def test_invalid_json_first_page_exits(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_invalid_json_mid_pagination_returns_partial(self):
        page1 = [{"id": i} for i in range(100)]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(stdout="not json")

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "scripts.github_core.api.time.sleep"
        ):
            with pytest.warns(UserWarning, match="Invalid JSON"):
                result = gh_api_paginated("repos/o/r/issues")
        assert len(result) == 100

    def test_endpoint_with_query_params_uses_ampersand(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")) as mock:
            gh_api_paginated("repos/o/r/issues?state=open")
        call_args = mock.call_args[0][0]
        assert "&per_page=" in call_args[2]


# ---------------------------------------------------------------------------
# API: gh_graphql
# ---------------------------------------------------------------------------


class TestGhGraphQL:
    def test_simple_query(self):
        response = json.dumps({"data": {"viewer": {"login": "testuser"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            result = gh_graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "testuser"}}

    def test_with_string_variables(self):
        response = json.dumps({"data": {"repository": {"name": "ai-agents"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($owner: String!) { ... }", {"owner": "rjmurillo"})
        cmd = mock.call_args[0][0]
        assert "-f" in cmd
        assert "owner=rjmurillo" in cmd

    def test_with_int_variables(self):
        response = json.dumps({"data": {}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($num: Int!) { ... }", {"num": 42})
        cmd = mock.call_args[0][0]
        assert "-F" in cmd
        assert "num=42" in cmd

    def test_transport_error_raises(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { viewer { login } }")

    def test_graphql_level_error_raises(self):
        response = json.dumps({"data": None, "errors": [{"message": "Not found"}]})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            with pytest.raises(RuntimeError, match="GraphQL errors.*Not found"):
                gh_graphql("query { ... }")

    def test_invalid_json_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="Failed to parse"):
                gh_graphql("query { ... }")

    def test_retries_transient_504_then_succeeds(self):
        """A transient HTTP 504 followed by success returns data (issue #2631)."""
        ok = json.dumps({"data": {"viewer": {"login": "u"}}})
        responses = [
            _completed(rc=1, stderr="gh: We couldn't respond in time. (HTTP 504)"),
            _completed(stdout=ok),
        ]
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", side_effect=responses) as run_mock,
        ):
            result = gh_graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "u"}}
        assert run_mock.call_count == 2
        assert sleep_mock.call_count == 1

    def test_retries_exhausted_on_persistent_504_raises(self):
        """Three consecutive 504s exhaust the bounded retry and raise (issue #2631)."""
        resp = _completed(rc=1, stderr="gh: timeout (HTTP 504)")
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { viewer { login } }")
        assert run_mock.call_count == 3
        assert sleep_mock.call_count == 2

    def test_retries_on_502_503_500_and_429(self):
        """Each transient 5xx and 429 retries then succeeds (issue #2631)."""
        ok = json.dumps({"data": {}})
        for code in ("500", "502", "503", "429"):
            responses = [
                _completed(rc=1, stderr=f"server error (HTTP {code})"),
                _completed(stdout=ok),
            ]
            with (
                patch("scripts.github_core.api.time.sleep"),
                patch("subprocess.run", side_effect=responses) as run_mock,
            ):
                gh_graphql("query { x }")
            assert run_mock.call_count == 2, code

    def test_permanent_404_does_not_retry(self):
        """A permanent client error (404, not 5xx/429) fails fast without retry."""
        resp = _completed(rc=1, stderr="gh: Not Found (HTTP 404)")
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { x }")
        assert run_mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_graphql_level_error_does_not_retry(self):
        """A GraphQL-level error (HTTP 200 with errors) is permanent, no retry."""
        resp = _completed(stdout=json.dumps({"data": None, "errors": [{"message": "Bad"}]}))
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL errors"):
                gh_graphql("query { x }")
        assert run_mock.call_count == 1
        assert sleep_mock.call_count == 0


# ---------------------------------------------------------------------------
# API: _retry_after_delay
# ---------------------------------------------------------------------------


class TestRetryAfterDelay:
    def test_retry_after_header_overrides_backoff(self):
        """Retry-After: N in error text returns N, not the backoff."""
        delay = _retry_after_delay("gh: rate limited (HTTP 429)\nRetry-After: 42", 2.0)
        assert delay == 42.0

    def test_retry_after_case_insensitive(self):
        """Header matching is case-insensitive."""
        delay = _retry_after_delay("retry-after: 10", 5.0)
        assert delay == 10.0

    def test_no_retry_after_uses_jitter(self):
        """Without Retry-After, the returned delay is in [0, backoff]."""
        backoff = 4.0
        delays = [_retry_after_delay("server error (HTTP 503)", backoff) for _ in range(20)]
        assert all(0.0 <= d <= backoff for d in delays), delays
        # Jitter must not always return the same value (probability of 20 identical
        # draws from uniform(0, 4) is negligible).
        assert len(set(delays)) > 1, "jitter produced identical values - check random source"

    def test_no_retry_after_empty_text(self):
        """Empty error text returns a value in [0, backoff]."""
        delay = _retry_after_delay("", 2.0)
        assert 0.0 <= delay <= 2.0


# ---------------------------------------------------------------------------
# API: get_all_prs_with_comments
# ---------------------------------------------------------------------------


class TestGetAllPRsWithComments:
    def _make_pr(self, number: int, updated: str, has_comments: bool = True):
        threads = []
        if has_comments:
            threads = [
                {
                    "isResolved": False,
                    "isOutdated": False,
                    "comments": {
                        "nodes": [
                            {
                                "id": "c1",
                                "body": "fix this",
                                "author": {"login": "reviewer"},
                                "createdAt": updated,
                                "path": "file.py",
                            }
                        ]
                    },
                }
            ]
        return {
            "number": number,
            "title": f"PR #{number}",
            "state": "OPEN",
            "author": {"login": "author"},
            "createdAt": updated,
            "updatedAt": updated,
            "mergedAt": None,
            "closedAt": None,
            "reviewThreads": {"nodes": threads},
        }

    def test_returns_prs_with_comments(self):
        pr = self._make_pr(1, "2026-01-15T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_excludes_prs_without_comments(self):
        pr_with = self._make_pr(1, "2026-01-15T00:00:00Z", has_comments=True)
        pr_without = self._make_pr(2, "2026-01-15T00:00:00Z", has_comments=False)
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr_with, pr_without],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 1

    def test_raises_when_repository_is_null(self):
        graphql_response = {"data": {"repository": None}}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            with pytest.raises(RuntimeError, match="not found or not accessible"):
                get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))

    def test_raises_when_pull_requests_is_null(self):
        graphql_response = {"data": {"repository": {"pullRequests": None}}}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            with pytest.raises(RuntimeError, match="Could not retrieve pull requests"):
                get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))

    def test_stops_when_pr_older_than_since(self):
        old_pr = self._make_pr(1, "2025-01-01T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                        "nodes": [old_pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Issue comments
# ---------------------------------------------------------------------------


class TestGetIssueComments:
    def test_delegates_to_paginated(self):
        comments = [{"id": 1, "body": "hello"}]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(comments))):
            result = get_issue_comments("owner", "repo", 42)
        assert result == comments


class TestUpdateIssueComment:
    def test_success(self):
        response = {"id": 123, "body": "updated"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))):
            result = update_issue_comment("owner", "repo", 123, "updated")
        assert result["body"] == "updated"

    def test_403_exits_code_4(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="HTTP 403: Forbidden"),
        ):
            with pytest.raises(SystemExit) as exc:
                update_issue_comment("owner", "repo", 123, "text")
            assert exc.value.code == 4

    def test_generic_api_error_exits_code_3(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="HTTP 500: Internal Server Error"),
        ):
            with pytest.raises(SystemExit) as exc:
                update_issue_comment("owner", "repo", 123, "text")
            assert exc.value.code == 3

    def test_sends_payload_via_stdin(self):
        response = {"id": 1, "body": "test"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))) as mock:
            update_issue_comment("owner", "repo", 1, "test body")
        assert mock.call_args.kwargs.get("input") == json.dumps({"body": "test body"})

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                update_issue_comment("owner", "repo", 123, "text")


class TestCreateIssueComment:
    def test_success(self):
        response = {"id": 999, "body": "new comment"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))):
            result = create_issue_comment("owner", "repo", 42, "new comment")
        assert result["body"] == "new comment"

    def test_api_failure_exits_3(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                create_issue_comment("owner", "repo", 42, "text")
            assert exc.value.code == 3

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                create_issue_comment("owner", "repo", 42, "text")


# ---------------------------------------------------------------------------
# 403 Pattern matching (ported from Pester behavioral tests)
# ---------------------------------------------------------------------------


class Test403PatternMatching:
    @pytest.mark.parametrize(
        "error_msg",
        [
            "HTTP 403: Forbidden",
            "status: 403",
            "gh: Resource not accessible by integration (HTTP 403)",
            "403 Forbidden",
            "FORBIDDEN",
            "Forbidden",
            "Error code: 403",
        ],
    )
    def test_detects_403_errors(self, error_msg: str):
        assert _403_PATTERN.search(error_msg) is not None

    @pytest.mark.parametrize(
        "error_msg",
        [
            "HTTP 401: Not authenticated",
            "HTTP 500: Internal Server Error",
            "Connection refused",
            "Comment ID 4030 not found",
            "Reference 1403245 is invalid",
        ],
    )
    def test_rejects_non_403_errors(self, error_msg: str):
        assert _403_PATTERN.search(error_msg) is None


# ---------------------------------------------------------------------------
# Trusted sources
# ---------------------------------------------------------------------------


class TestGetTrustedSourceComments:
    def test_filters_to_trusted_users(self):
        comments = [
            {"id": 1, "user": {"login": "alice"}},
            {"id": 2, "user": {"login": "bob"}},
            {"id": 3, "user": {"login": "alice"}},
        ]
        result = get_trusted_source_comments(comments, ["alice"])
        assert len(result) == 2
        assert all(c["user"]["login"] == "alice" for c in result)

    def test_empty_comments_returns_empty(self):
        assert get_trusted_source_comments([], ["alice"]) == []

    def test_no_matches_returns_empty(self):
        comments = [{"id": 1, "user": {"login": "eve"}}]
        assert get_trusted_source_comments(comments, ["alice"]) == []


# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------


class TestGetBotAuthorsConfig:
    def test_returns_dict_with_required_keys(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n")
        # Mock _find_repo_root to skip CWE-22 check (tmp_path is outside repo)
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert set(result.keys()) == {"reviewer", "automation", "repository"}

    def test_each_category_has_entries(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - r1\n  - r2\nautomation:\n  - a1\nrepository:\n  - p1\n")
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert len(result["reviewer"]) == 2
        assert len(result["automation"]) == 1
        assert len(result["repository"]) == 1

    def test_caches_result(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n")
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            r1 = get_bot_authors_config(config_path=str(config), force=True)
            r2 = get_bot_authors_config(config_path=str(config))
        assert r1 is r2

    def test_force_reloads(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - old\nautomation:\n  - a\nrepository:\n  - r\n")
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            get_bot_authors_config(config_path=str(config), force=True)
            config.write_text("reviewer:\n  - new\nautomation:\n  - a\nrepository:\n  - r\n")
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert "new" in result["reviewer"]

    def test_falls_back_to_defaults_when_missing(self):
        result = get_bot_authors_config(config_path="/nonexistent/config.yml", force=True)
        assert "coderabbitai[bot]" in result["reviewer"]

    def test_falls_back_on_empty_config(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("")
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert result == _DEFAULT_BOTS

    def test_path_traversal_uses_defaults(self, tmp_path: Path):
        # Create a file that resolves outside the "repo root"
        outside = tmp_path / "outside.yml"
        outside.write_text("reviewer:\n  - evil\n")
        # Set repo root to a subdirectory so the file is outside it
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with patch(
            "scripts.github_core.bot_config._find_repo_root",
            return_value=str(repo_root),
        ):
            with pytest.warns(UserWarning, match="outside repository root"):
                result = get_bot_authors_config(config_path=str(outside), force=True)
        assert result == _DEFAULT_BOTS


class TestGetBotAuthors:
    def test_all_returns_combined_sorted(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("all")
        assert "coderabbitai[bot]" in result
        assert "github-actions[bot]" in result
        assert "rjmurillo-bot" in result
        assert result == sorted(result)

    def test_reviewer_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("reviewer")
        assert "coderabbitai[bot]" in result
        assert "github-copilot[bot]" in result
        assert "github-actions[bot]" not in result
        assert "rjmurillo-bot" not in result

    def test_automation_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("automation")
        assert "github-actions[bot]" in result
        assert "dependabot[bot]" in result
        assert "coderabbitai[bot]" not in result

    def test_repository_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("repository")
        assert "rjmurillo-bot" in result
        assert "copilot-swe-agent[bot]" in result
        assert "github-actions[bot]" not in result

    def test_default_is_all(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors()
        assert len(result) == len(set(b for v in _DEFAULT_BOTS.values() for b in v))


# ---------------------------------------------------------------------------
# PR review threads
# ---------------------------------------------------------------------------


class TestSafeLogStr:
    def test_strips_carriage_return(self):
        assert safe_log_str("a\rb") == "a\\rb"

    def test_strips_newline(self):
        assert safe_log_str("a\nb") == "a\\nb"

    def test_strips_crlf_log_forging_attempt(self):
        """Defense against CWE-117: an attacker-controlled error message
        embedding `\\r\\n op=review_threads_failed reason=fake` must not
        produce a forged log line.
        """
        forged = "real_error\r\n op=review_threads_failed reason=fake"
        sanitized = safe_log_str(forged)
        assert "\r" not in sanitized
        assert "\n" not in sanitized
        assert sanitized.startswith("real_error\\r\\n")

    def test_handles_non_string(self):
        assert safe_log_str(42) == "42"
        assert safe_log_str(RuntimeError("oops")) == "oops"


class TestFetchStatus:
    def test_str_enum_values(self):
        assert FetchStatus.OK == "ok"
        assert FetchStatus.TRANSPORT_ERROR == "transport_error"
        assert FetchStatus.STRUCTURAL_MISSING == "structural_missing"

    @pytest.mark.parametrize(
        ("member", "rendered"),
        [
            (FetchStatus.OK, "ok"),
            (FetchStatus.TRANSPORT_ERROR, "transport_error"),
            (FetchStatus.STRUCTURAL_MISSING, "structural_missing"),
        ],
    )
    def test_rendering_a_member_yields_its_value(self, member, rendered):
        """Equality is not the contract; rendering is, and they came apart.

        Dropping `enum.StrEnum` for `str, Enum` at the 3.10 portability floor
        keeps every equality comparison working and silently changes
        `str(FetchStatus.OK)` from "ok" to "FetchStatus.OK", because StrEnum
        inherits `str.__str__` and a plain `str, Enum` takes `Enum.__str__`.
        The three assertions above passed through that whole change. Every log
        line, f-string, and serialized field carrying this value changed shape,
        and FetchStatus is exported from `github_core`, so the blast radius is
        outside this module (Copilot review on PR #5509).
        """
        assert str(member) == rendered
        assert f"{member}" == rendered
        assert format(member) == rendered
        assert "{}".format(member) == rendered  # noqa: UP032

    def test_typo_raises_attribute_error(self):
        """Typo on a StrEnum member is a fail-fast attribute error,
        unlike a bare-string sentinel which would silently miss.
        """
        with pytest.raises(AttributeError):
            _ = FetchStatus.OK_TYPO


class TestCountUnresolvedThreads:
    def test_empty_list(self):
        assert count_unresolved_threads([]) == 0

    def test_all_resolved(self):
        nodes = [{"isResolved": True}, {"isResolved": True}]
        assert count_unresolved_threads(nodes) == 0

    def test_all_unresolved(self):
        nodes = [{"isResolved": False}, {"isResolved": False}]
        assert count_unresolved_threads(nodes) == 2

    def test_mixed(self):
        nodes = [
            {"isResolved": True},
            {"isResolved": False},
            {"isResolved": False},
        ]
        assert count_unresolved_threads(nodes) == 2

    def test_missing_is_resolved_defaults_to_resolved(self):
        """A malformed thread without isResolved defaults to resolved
        (treated as not unresolved). Prevents a missing field from
        silently inflating the unresolved count.
        """
        nodes = [{}, {"id": "x"}]
        assert count_unresolved_threads(nodes) == 0

    def test_explicit_null_is_resolved_defaults_to_resolved(self):
        """An explicit null isResolved from the GraphQL payload is treated the
        same as a missing field (resolved), so it is not counted as unresolved.
        """
        nodes = [{"isResolved": None}, {"id": "x", "isResolved": None}]
        assert count_unresolved_threads(nodes) == 0


class TestFilterUnresolvedThreads:
    def test_returns_only_unresolved(self):
        nodes = [
            {"id": "a", "isResolved": True},
            {"id": "b", "isResolved": False},
            {"id": "c", "isResolved": False},
        ]
        result = filter_unresolved_threads(nodes)
        assert [t["id"] for t in result] == ["b", "c"]

    def test_count_and_filter_agree(self):
        """The count helper and filter helper share the rule, so
        ``count == len(filter)`` for any input. This locks the DRY
        invariant in a test.
        """
        nodes = [
            {"isResolved": True},
            {"isResolved": False},
            {},
            {"isResolved": False},
            {"isResolved": None},
        ]
        assert count_unresolved_threads(nodes) == len(filter_unresolved_threads(nodes))


class TestGetUnresolvedReviewThreads:
    def test_returns_unresolved_threads(self):
        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    _thread("t1", False, 1),
                                    _thread("t2", True, 2),
                                    _thread("t3", False, 3),
                                ]
                            }
                        }
                    }
                }
            }
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert len(result) == 2
        assert all(not t["isResolved"] for t in result)

    def test_returns_empty_on_all_resolved(self):
        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    _thread("t1", True, 1),
                                ]
                            }
                        }
                    }
                }
            }
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_no_threads(self):
        graphql_response = json.dumps(
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}}
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.warns(UserWarning, match="Failed to query review threads.*network error"):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_never_returns_none(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fail")):
            with pytest.warns(UserWarning):
                result = get_unresolved_review_threads("owner", "repo", 1)
        assert result is not None
        assert isinstance(result, list)

    def test_paginates_until_has_next_page_false(self):
        """Closes PR #1887's pagination cliff: callers see threads on page 2+.

        Two pages: 100 unresolved threads on page 1, 5 unresolved on page 2.
        The PR #1887 retro records that the prior single-page query missed
        the second page entirely and reported "0 unresolved" while threads
        sat there. With pagination, all 105 are returned.
        """
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "CURSOR_PAGE_2",
                                },
                                "nodes": [_thread(f"page1-{i}", False, i) for i in range(100)],
                            }
                        }
                    }
                }
            }
        )
        page_two = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                                "nodes": [_thread(f"page2-{i}", False, 1000 + i) for i in range(5)],
                            }
                        }
                    }
                }
            }
        )

        responses = [_completed(stdout=page_one), _completed(stdout=page_two)]
        with patch("subprocess.run", side_effect=responses) as mock_run:
            result = get_unresolved_review_threads("owner", "repo", 42)

        assert mock_run.call_count == 2, (
            "Pagination loop did not call gh twice; pageInfo.hasNextPage=true was ignored"
        )
        assert len(result) == 105, (
            f"Expected 105 unresolved threads across pages, got {len(result)}"
        )
        page1_ids = {f"page1-{i}" for i in range(100)}
        page2_ids = {f"page2-{i}" for i in range(5)}
        actual_ids = {t["id"] for t in result}
        assert actual_ids == page1_ids | page2_ids, "Page-2 thread IDs missing from result"

    def test_pagination_passes_cursor_to_second_page(self):
        """The endCursor from page 1 must be sent as $cursor on page 2.

        Without that, GitHub returns page 1 again forever. We assert the
        gh argv on call #2 contains the cursor value from page 1.
        """
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "CURSOR_FROM_PAGE_1",
                                },
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )
        page_two = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [],
                            }
                        }
                    }
                }
            }
        )

        responses = [_completed(stdout=page_one), _completed(stdout=page_two)]
        with patch("subprocess.run", side_effect=responses) as mock_run:
            get_unresolved_review_threads("owner", "repo", 42)

        # Inspect the second subprocess.run call's argv for the cursor value.
        second_call_argv = mock_run.call_args_list[1][0][0]
        joined = " ".join(second_call_argv)
        assert "cursor=CURSOR_FROM_PAGE_1" in joined, (
            f"Cursor from page 1 not propagated to page 2 query; argv was: {joined}"
        )

    def test_pagination_stops_when_endcursor_is_empty(self):
        """Defensive: a hasNextPage=true with empty endCursor must not loop forever."""
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": True, "endCursor": ""},
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )

        with patch("subprocess.run", side_effect=[_completed(stdout=page_one)]) as mock_run:
            result = get_unresolved_review_threads("owner", "repo", 42)

        assert mock_run.call_count == 1, "Loop did not stop on empty endCursor"
        assert len(result) == 1

    def test_graphql_error_logs_reason_at_api_level(self, caplog):
        """The api.py-level _fetch_review_threads_page logs reason=graphql_error
        with op=review_threads_failed, distinct from the script-level logger.
        Without this, an operator grepping api.py logs for the failure reason
        would not see why a transport error occurred.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="rate limit"),
            ):
                with pytest.warns(UserWarning):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any(
            "op=review_threads_failed" in r.message and "reason=graphql_error" in r.message
            for r in caplog.records
        ), "api.py-level transport error must log op=review_threads_failed reason=graphql_error"

    def test_field_missing_logs_reason_at_api_level(self, caplog):
        """When pullRequest is null, api.py path emits reason=pr_not_found."""
        import logging

        graphql_response = json.dumps({"data": {"repository": {"pullRequest": None}}})
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(stdout=graphql_response),
            ):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any("reason=pr_not_found" in r.message for r in caplog.records), (
            "Null pullRequest must log reason=pr_not_found at api.py level"
        )

    def test_nodes_missing_logs_reason_at_api_level(self, caplog):
        """reviewThreads.nodes is null (distinct from connection-missing).

        The skill-side has 4 reasons (pr_not_found, field_missing,
        nodes_missing, graphql_error). api.py must emit the same taxonomy
        so operators grepping by reason find both surfaces.
        """
        import logging

        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": None,
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                }
            }
        )
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(stdout=graphql_response),
            ):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any("reason=nodes_missing" in r.message for r in caplog.records), (
            "Null reviewThreads.nodes must log reason=nodes_missing"
        )

    def test_cursor_missing_emits_warning_and_logs_reason(self, caplog):
        """When hasNextPage=true but endCursor is empty/null, the loop must
        emit a warnings.warn AND a structured log line with
        ``op=review_threads_failed reason=cursor_missing`` before breaking,
        so callers cannot mistake the partial result for a complete one.
        Defensive guardrail flagged by Copilot review on PR #1897.
        """
        import logging

        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": True, "endCursor": ""},
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                side_effect=[_completed(stdout=page_one)],
            ) as mock_run:
                with pytest.warns(UserWarning, match=r"cursor_missing"):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert mock_run.call_count == 1
        assert len(result) == 1
        assert any("reason=cursor_missing" in r.message for r in caplog.records), (
            "cursor_missing branch must emit op=review_threads_failed reason=cursor_missing"
        )

    def test_mid_pagination_structural_failure_emits_warning(self, caplog):
        """Page 1 OK, page 2 structurally invalid → caller sees a warning.

        A structurally invalid page-2 response (missing repository.pullRequest
        block, etc.) on a multi-page query truncates the aggregate. Without
        the warning the loop just breaks and callers see N partial threads
        with no signal that pages 2+ were dropped.
        """
        import logging

        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": True, "endCursor": "cur1"},
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )
        page_two_invalid = json.dumps({"data": {"repository": None}})
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                side_effect=[
                    _completed(stdout=page_one),
                    _completed(stdout=page_two_invalid),
                ],
            ):
                with pytest.warns(UserWarning, match=r"structural_failure"):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert len(result) == 1, "page 1 result must be preserved on page 2 failure"
        assert any("reason=structural_failure" in r.message for r in caplog.records), (
            "mid-pagination structural failure must emit reason=structural_failure"
        )

    def test_pagination_cap_emits_warning_and_stops(self):
        """At-cap exit must warn the caller, not silently truncate.

        The PR #1887 retro records that a silent first:100 truncation hid 6+
        unresolved threads. A silent at-cap exit at _REVIEW_THREADS_MAX_PAGES
        would reproduce the same false-zero failure mode at the 5000-thread
        boundary. This test asserts: (1) the loop stops at exactly the cap;
        (2) warnings.warn fires with a message naming the cap and the PR;
        (3) the partial result is still returned (not discarded).
        """
        from scripts.github_core.api import _REVIEW_THREADS_MAX_PAGES

        # Every page reports hasNextPage=True and a fresh cursor; one
        # unresolved thread per page so we can count.
        def _page_response(page_idx: int) -> str:
            return json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": f"CURSOR_PAGE_{page_idx + 1}",
                                    },
                                    "nodes": [_thread(f"page{page_idx}-t", False, page_idx)],
                                }
                            }
                        }
                    }
                }
            )

        # Provide cap+5 pages. Loop must stop at cap.
        responses = [
            _completed(stdout=_page_response(i)) for i in range(_REVIEW_THREADS_MAX_PAGES + 5)
        ]

        with patch("subprocess.run", side_effect=responses) as mock_run:
            with pytest.warns(UserWarning, match=r"Hit _REVIEW_THREADS_MAX_PAGES"):
                result = get_unresolved_review_threads("owner", "repo", 1894)

        assert mock_run.call_count == _REVIEW_THREADS_MAX_PAGES, (
            f"Loop did not stop at cap; called {mock_run.call_count} times "
            f"(expected {_REVIEW_THREADS_MAX_PAGES})"
        )
        assert len(result) == _REVIEW_THREADS_MAX_PAGES, (
            "Partial threads must be returned alongside the warning, not discarded"
        )


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------

RATE_LIMIT_ALL_OK = json.dumps(
    {
        "resources": {
            "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)

RATE_LIMIT_CORE_LOW = json.dumps(
    {
        "resources": {
            "core": {"remaining": 50, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)

RATE_LIMIT_MISSING_RESOURCE = json.dumps(
    {
        "resources": {
            "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)


class TestCheckWorkflowRateLimit:
    def test_success_all_above_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY
        assert result.core_remaining == 5000

    def test_failure_core_below_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert result.resources["core"]["Passed"] is False

    def test_custom_thresholds_pass(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 10})
        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY

    def test_custom_thresholds_fail(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 100})
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED

    def test_markdown_summary(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert "API Rate Limit Status" in result.summary_markdown
        assert "| Resource |" in result.summary_markdown
        assert "OK" in result.summary_markdown

    def test_missing_resource_warns(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_MISSING_RESOURCE)):
            with pytest.warns(UserWarning, match="code_search"):
                result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE

    def test_raises_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="API error")):
            with pytest.raises(RuntimeError, match="Failed to fetch rate limits"):
                check_workflow_rate_limit()

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                check_workflow_rate_limit()

    def test_returns_rate_limit_result_type(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert isinstance(result, RateLimitResult)

    def test_null_resources_does_not_crash(self):
        """An explicit null ``resources`` from the API must not raise. Every
        resource reads as missing (warns, fails) and core_remaining is 0.
        """
        payload = json.dumps({"resources": None})
        with patch("subprocess.run", return_value=_completed(stdout=payload)):
            with pytest.warns(UserWarning):
                result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE
        assert result.core_remaining == 0


# ---------------------------------------------------------------------------
# Formatting: Priority emoji
# ---------------------------------------------------------------------------


class TestGetPriorityEmoji:
    def test_p0_fire(self):
        assert get_priority_emoji("P0") == "\U0001f525"

    def test_p1_exclamation(self):
        assert get_priority_emoji("P1") == "\u2757"

    def test_p2_dash(self):
        assert get_priority_emoji("P2") == "\u2796"

    def test_p3_down_arrow(self):
        assert get_priority_emoji("P3") == "\u2b07\ufe0f"

    def test_unknown_question_mark(self):
        assert get_priority_emoji("unknown") == "\u2754"


# ---------------------------------------------------------------------------
# Formatting: Reaction emoji
# ---------------------------------------------------------------------------


class TestGetReactionEmoji:
    def test_thumbs_up(self):
        assert get_reaction_emoji("+1") == "\U0001f44d"

    def test_thumbs_down(self):
        assert get_reaction_emoji("-1") == "\U0001f44e"

    def test_laugh(self):
        assert get_reaction_emoji("laugh") == "\U0001f604"

    def test_confused(self):
        assert get_reaction_emoji("confused") == "\U0001f615"

    def test_heart(self):
        assert get_reaction_emoji("heart") == "\u2764\ufe0f"

    def test_hooray(self):
        assert get_reaction_emoji("hooray") == "\U0001f389"

    def test_rocket(self):
        assert get_reaction_emoji("rocket") == "\U0001f680"

    def test_eyes(self):
        assert get_reaction_emoji("eyes") == "\U0001f440"

    def test_unknown_returns_input(self):
        assert get_reaction_emoji("custom") == "custom"


class TestYamlFallback:
    """No-PyYAML fallback path (issue #1844).

    When PyYAML is not importable, bot_config must still load authors via
    the vendored _parse_simple_yaml and produce the same result.
    """

    def test_parse_simple_yaml_matches_yaml_safe_load(self) -> None:
        import yaml as _yaml

        text = (_REPO_ROOT / ".github" / "bot-authors.yml").read_text(encoding="utf-8")
        reference = _yaml.safe_load(text)
        assert bot_config._parse_simple_yaml(text) == reference

    def test_get_bot_authors_config_without_yaml(self, monkeypatch) -> None:
        with_yaml = bot_config.get_bot_authors_config(force=True)
        monkeypatch.setattr(bot_config, "yaml", None)
        without_yaml = bot_config.get_bot_authors_config(force=True)
        assert without_yaml == with_yaml

    def test_is_bot_without_yaml(self, monkeypatch) -> None:
        monkeypatch.setattr(bot_config, "yaml", None)
        bot_config.get_bot_authors_config(force=True)
        assert bot_config.is_bot("coderabbitai[bot]")
        assert not bot_config.is_bot("octocat-human")

    def test_missing_file_without_yaml_uses_defaults(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(bot_config, "yaml", None)
        missing = str(tmp_path / "none.yml")
        cfg = bot_config.get_bot_authors_config(config_path=missing, force=True)
        assert cfg == bot_config._DEFAULT_BOTS


class TestParseSimpleYaml:
    """Unit coverage for the vendored YAML-subset parser (issue #1844)."""

    def test_block_list(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo\n  - bar\n") == {
            "bots": ["foo", "bar"]
        }

    def test_inline_comment_stripped_from_item(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo  # note\n") == {"bots": ["foo"]}

    def test_comments_and_blanks_ignored(self) -> None:
        text = "# header\n\nbots:\n  - foo\n\n  - bar\n# trailer\n"
        assert bot_config._parse_simple_yaml(text) == {"bots": ["foo", "bar"]}

    def test_item_with_space_and_brackets_preserved(self) -> None:
        text = "bots:\n  - Copilot   # no suffix\n  - renovate[bot]\n"
        assert bot_config._parse_simple_yaml(text) == {"bots": ["Copilot", "renovate[bot]"]}

    def test_literal_hash_in_item_preserved(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo#bar\n") == {"bots": ["foo#bar"]}

    def test_inline_scalar_value(self) -> None:
        assert bot_config._parse_simple_yaml("name: value\n") == {"name": "value"}

    def test_quoted_value_unwrapped(self) -> None:
        assert bot_config._parse_simple_yaml('name: "value"\n') == {"name": "value"}

    def test_quoted_item_unwrapped(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - 'foo'\n") == {"bots": ["foo"]}

    def test_hash_inside_quoted_item_preserved(self) -> None:
        # A # inside quotes is literal content, not a comment marker.
        assert bot_config._parse_simple_yaml("bots:\n  - 'foo # bar'\n") == {"bots": ["foo # bar"]}
        assert bot_config._parse_simple_yaml('name: "value # note"\n') == {"name": "value # note"}

    def test_empty_text(self) -> None:
        assert bot_config._parse_simple_yaml("") == {}

    def test_orphan_item_without_key_ignored(self) -> None:
        assert bot_config._parse_simple_yaml("- foo\n") == {}

    def test_bare_scalar_text_yields_empty(self) -> None:
        # A document with no `key:` mapping has nothing to collect; the
        # caller then falls back to defaults via the empty-dict guard.
        assert bot_config._parse_simple_yaml("just a string\n") == {}

    def test_mismatched_quote_left_intact(self) -> None:
        # Only a matched surrounding pair is stripped.
        assert bot_config._parse_simple_yaml("bots:\n  - \"foo'\n") == {"bots": ["\"foo'"]}

    def test_colon_value_without_space(self) -> None:
        # Per YAML spec, a colon without a following space is part of a plain
        # scalar, not a key-value separator. yaml.safe_load("name:value\n")
        # returns the string "name:value", not a dict. Our parser follows suit
        # by returning {} for non-mapping documents.
        assert bot_config._parse_simple_yaml("name:value\n") == {}

    def test_crlf_line_endings(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\r\n  - foo\r\n") == {"bots": ["foo"]}


class TestMirrorParity:
    """The install mirrors must equal the canonical loader's sync transform.

    scripts/sync_plugin_lib.py (_transform_file) converts intra-package absolute
    imports to relative ones. The mirrors must equal that output exactly so
    they cannot drift from the real sync contract.
    """

    def test_mirrors_match_sync_transform(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sync_plugin_lib", _REPO_ROOT / "scripts" / "sync_plugin_lib.py"
        )
        assert spec is not None
        assert spec.loader is not None
        spl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(spl)

        src = _REPO_ROOT / "scripts/github_core/bot_config.py"
        expected = spl._transform_file(src, "scripts/github_core")
        for mirror in (
            ".claude/lib/github_core/bot_config.py",
            "src/copilot-cli/lib/github_core/bot_config.py",
        ):
            assert (_REPO_ROOT / mirror).read_text(encoding="utf-8") == expected, mirror


# ---------------------------------------------------------------------------
# Captured-text decoding across github_core
# ---------------------------------------------------------------------------


class TestCapturedTextDecoding:
    """Every captured-text reader in this package pins its codec.

    Without an explicit ``encoding`` Python decodes with the locale's
    preferred codec, so a cp1252 or cp932 runner turns the same bytes into
    different characters without raising. `gh` emits raw UTF-8 and `git`
    emits raw filesystem bytes, so both readers are exposed.
    """

    def test_rate_limit_pins_utf8(self):
        from scripts.github_core import rate_limit

        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)) as run:
            rate_limit._fetch_rate_limit()
        assert run.call_args.kwargs.get("encoding") == "utf-8"
        assert "errors" not in run.call_args.kwargs

    def test_repo_root_pins_utf8(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=str(tmp_path))) as run:
            repo.get_repo_root()
        assert run.call_args.kwargs.get("encoding") == "utf-8"
        assert "errors" not in run.call_args.kwargs

    def test_repo_root_returns_none_when_git_output_will_not_decode(self):
        """Strict decoding must not crash a helper documented to return None.

        Filesystem paths on POSIX are bytes, so a checkout under a name that is
        not valid UTF-8 makes ``subprocess.run`` raise while decoding. The
        function promises ``None`` on failure, and every caller anchors paths on
        the result, so an escaping decode error would take out unrelated tools.
        """
        from scripts.github_core import repo

        boom = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
        with patch("subprocess.run", side_effect=boom):
            assert repo.get_repo_root() is None

    def test_repo_root_survives_a_non_ascii_path(self, tmp_path: Path):
        """The repo root seeds every derived path, so a mojibake read is load-bearing."""
        from scripts.github_core import repo

        root = tmp_path / "\u30d7\u30ed\u30b8\u30a7\u30af\u30c8"
        root.mkdir()
        with patch("subprocess.run", return_value=_completed(stdout=f"{root}\n")):
            assert repo.get_repo_root() == root


class TestEscapedNewlineBodyError:
    """Guard against inline --body strings that carry literal backslash-n.

    Issue #3777. Two shipped issues (#3598, #3646) reached GitHub with their
    line breaks written as the two characters backslash and n, so GitHub
    rendered each as one unbroken paragraph and dropped every heading, list
    and table. Nothing errored at the time.

    The premise recorded in #3777 ("0 real newlines") is wrong and was
    re-measured before this guard was written: #3598 carries 15 literal
    sequences and 1 real newline, #3646 carries 9 and 1, in both cases a
    trailing newline supplied by the API. A naive ``"\\n" not in body``
    check therefore misses both, which is why the predicate strips first.
    """

    def test_flags_escaped_newlines_with_no_real_break(self) -> None:
        body = "## Summary\\n\\nSome text\\n- item"
        message = validation.escaped_newline_body_error(body)
        assert message is not None
        assert "3 literal backslash-n" in message
        assert "--body-file" in message

    def test_flags_the_measured_shape_of_issue_3598(self) -> None:
        """Trailing-newline-only bodies are the real-world failure shape."""
        body = "## Summary\\n\\nDetail\\n" + "\n"
        assert validation.escaped_newline_body_error(body) is not None

    def test_allows_escaped_newlines_alongside_real_ones(self) -> None:
        """A code fence may legitimately show a backslash-n sequence."""
        body = '## Notes\n\n```python\nprint("a\\nb")\n```\n'
        assert validation.escaped_newline_body_error(body) is None

    def test_allows_a_normal_multiline_body(self) -> None:
        assert validation.escaped_newline_body_error("## H\n\ntext\n") is None

    def test_allows_a_single_line_body_without_escapes(self) -> None:
        assert validation.escaped_newline_body_error("Just one line.") is None

    def test_allows_empty_and_none_bodies(self) -> None:
        """Empty-body rejection belongs to the callers, not this predicate."""
        assert validation.escaped_newline_body_error("") is None
        assert validation.escaped_newline_body_error(None) is None

    def test_message_counts_every_occurrence(self) -> None:
        message = validation.escaped_newline_body_error("a\\nb\\nc")
        assert message is not None
        assert "2 literal backslash-n" in message


class TestEscapedNewlineGuardIsWiredAtEveryInlineBodySite:
    """Isolating control: each caller must reject a corrupt inline body.

    A shared predicate that no caller invokes fixes nothing. Issue #3777 is
    about the six scripts that pass an inline ``--body`` straight to gh, so
    the guard is only load-bearing if every one of them calls it.
    """

    # Three sites reach the guard through inline_body_error, which folds the
    # empty-body check in with it so the host main() spends one branch
    # instead of two. Two sites call escaped_newline_body_error directly
    # because their empty-body rule differs (new_issue.py validates only the
    # title; edit_issue_body.py rejects empty strings with exit 1).
    _SITE_ENTRY_POINTS = {
        "issue/new_issue.py": "escaped_newline_body_error",
        "issue/edit_issue_body.py": "escaped_newline_body_error",
        "issue/post_issue_comment.py": "inline_body_error",
        "pr/post_pr_comment_reply.py": "inline_body_error",
        "pr/add_pr_review_thread_reply.py": "inline_body_error",
    }

    def _script(self, rel: str) -> str:
        root = Path(__file__).resolve().parents[1]
        path = root / ".claude" / "skills" / "github" / "scripts" / rel
        assert path.is_file(), f"missing script: {path}"
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("rel,entry", sorted(_SITE_ENTRY_POINTS.items()))
    def test_site_imports_and_calls_the_shared_predicate(self, rel: str, entry: str) -> None:
        source = self._script(rel)
        assert "from github_core.validation import" in source, rel
        tree = ast.parse(source)
        called = any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == entry
            for node in ast.walk(tree)
        )
        assert called, f"{rel} never calls {entry}"

    def test_pr_copy_cites_the_canonical_source(self) -> None:
        """The PR path carries a second copy and must say where it came from.

        new_pr.py resolves only its own directory on sys.path, so importing
        github_core would mean adding the lib bootstrap the other scripts
        use, which hard-exits 2 whenever .claude/lib is absent. On the push
        path that trades a rendering bug for an outage. The copy therefore
        lives in the sibling module new_pr.py already imports from, and the
        citation is what keeps the two findable from each other.

        Behaviour is pinned by
        tests/test_new_pr.py::TestValidation6EscapedNewlineCheck; only the
        cross-reference is asserted here, because no runtime test can.
        """
        source = self._script("pr/validate_pr_description.py")
        assert "scripts/github_core/validation.py::escaped_newline_body_error" in source
        assert "validate_no_escaped_newlines" in self._script("pr/new_pr.py")


class TestInlineBodyError:
    """The folded predicate the three symmetric callers use.

    Issue #3777. Both rejections are reported through one branch so the
    host main() functions, all of which already carry a noqa: C901, do not
    grow another. post_issue_comment.py::main measured 21 before this change
    and 20 after.

    Check order is deliberately untested. A body that strips to empty cannot
    contain a literal backslash-n, because neither backslash nor n is
    whitespace, so the two conditions are mutually exclusive. Verified
    exhaustively over 9331 bodies drawn from space, tab, newline, backslash,
    n and x up to length 5: zero satisfy both. Swapping the arms is an
    equivalent mutant, and a test asserting the order would never fail.
    """

    def test_rejects_an_empty_body(self) -> None:
        assert validation.inline_body_error("") == "Body cannot be empty."

    def test_rejects_a_none_body(self) -> None:
        assert validation.inline_body_error(None) == "Body cannot be empty."

    def test_rejects_a_whitespace_only_body(self) -> None:
        assert validation.inline_body_error("  \n\t ") == "Body cannot be empty."

    def test_rejects_escaped_newlines(self) -> None:
        message = validation.inline_body_error("## H\\n\\ntext")
        assert message is not None
        assert "literal backslash-n" in message

    def test_allows_a_normal_body(self) -> None:
        assert validation.inline_body_error("## H\n\ntext\n") is None


class TestResolveRepoRoot:
    """`None` alone cannot distinguish "no repository" from "git failed".

    `is_safe_file_path` uses the repository root as a containment base for a
    path-traversal check (CWE-22). Falling back to the working directory is
    correct only when git has confirmed there is no repository. When git could
    not answer, the root is unknown rather than absent, and substituting a
    different base answers a question nobody asked.
    """

    def test_success_returns_root_and_ok(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=f"{tmp_path}\n")):
            assert repo.resolve_repo_root() == (tmp_path, REPO_ROOT_OK)

    def test_git_reporting_no_repository_is_distinguishable(self):
        from scripts.github_core import repo

        stderr = "fatal: not a git repository (or any of the parent directories): .git\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_NOT_A_REPO)

    def test_unrecognized_git_failure_fails_closed(self):
        """An exit code we cannot explain must not be read as "no repository"."""
        from scripts.github_core import repo

        stderr = "fatal: index file smaller than expected\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_empty_stderr_on_failure_fails_closed(self):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_timeout_is_git_failed(self):
        from scripts.github_core import repo

        boom = subprocess.TimeoutExpired(cmd=["git"], timeout=10)
        with patch("subprocess.run", side_effect=boom):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_missing_git_binary_is_git_failed(self):
        from scripts.github_core import repo

        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_undecodable_output_is_git_failed(self):
        from scripts.github_core import repo

        boom = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
        with patch("subprocess.run", side_effect=boom):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_locale_is_pinned_so_the_stderr_match_is_deterministic(self):
        """Git translates `fatal: not a git repository`. LC_ALL=C pins it.

        Without this the discriminator would silently degrade to "git failed"
        on a non-English runner, and every default-base containment check on
        that machine would start refusing.
        """
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="/tmp\n")) as run:
            repo.resolve_repo_root()
        assert run.call_args.kwargs["env"]["LC_ALL"] == "C"

    def test_inherited_environment_is_preserved(self):
        """Pinning the locale must not blank PATH and friends."""
        import os

        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="/tmp\n")) as run:
            repo.resolve_repo_root()
        env = run.call_args.kwargs["env"]
        for key in os.environ:
            if key != "LC_ALL":
                assert env[key] == os.environ[key]

    def test_stderr_match_is_case_insensitive(self):
        from scripts.github_core import repo

        stderr = "FATAL: NOT A GIT REPOSITORY\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_NOT_A_REPO)

    def test_relative_output_is_anchored_like_before(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="sub\n")):
            root, reason = repo.resolve_repo_root(start_dir=tmp_path)
        assert reason == REPO_ROOT_OK
        assert root == (tmp_path / "sub").resolve()

    def test_start_dir_is_forwarded(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=f"{tmp_path}\n")) as run:
            repo.resolve_repo_root(start_dir=tmp_path)
        assert run.call_args.args[0] == [
            "git",
            "-C",
            str(tmp_path),
            "rev-parse",
            "--show-toplevel",
        ]

    def test_get_repo_root_keeps_its_none_contract(self):
        """Every existing caller reads `None`; the wrapper must not change that."""
        from scripts.github_core import repo

        stderr = "fatal: not a git repository\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.get_repo_root() is None
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert repo.get_repo_root() is None

    def test_public_export_matches_the_module(self):
        from scripts.github_core import repo

        assert resolve_repo_root is repo.resolve_repo_root
