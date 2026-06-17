"""Tests for post_issue_comment.py."""

import json
import subprocess
from unittest.mock import patch

import pytest
from github_core.api import RepoInfo
from test_helpers import import_skill_script, make_completed_process


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    return import_skill_script("post_issue_comment", "issue")


class TestPrependMarker:
    def test_adds_marker_when_missing(self, _import_module):
        mod = _import_module
        result = mod._prepend_marker("body", "<!-- M -->")
        assert result == "<!-- M -->\n\nbody"

    def test_keeps_body_when_marker_present(self, _import_module):
        mod = _import_module
        body = "<!-- M -->\n\nbody"
        result = mod._prepend_marker(body, "<!-- M -->")
        assert result == body


class TestPermissionDetection:
    """Test that 403 patterns are detected via the _403_PATTERN regex."""

    def test_detects_403(self, _import_module):
        mod = _import_module
        assert mod._403_PATTERN.search("HTTP 403 Forbidden") is not None
        assert mod._403_PATTERN.search("Resource not accessible by integration") is not None

    def test_passes_non_403(self, _import_module):
        mod = _import_module
        assert mod._403_PATTERN.search("HTTP 404 Not Found") is None
        assert mod._403_PATTERN.search("success") is None


class TestPostIssueComment:
    """Tests for post_issue_comment.main."""

    def test_post_new_comment(self, _import_module, capsys):
        mod = _import_module
        response = {"id": 100, "html_url": "https://example.com/comment"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(response)
            )),
        ):
            rc = mod.main(["--issue", "1", "--body", "hello"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is True
        assert result["Data"]["comment_id"] == 100
        assert result["Data"]["skipped"] is False

    def test_skip_when_marker_exists(self, _import_module, capsys):
        mod = _import_module
        marker_html = "<!-- TEST-MARKER -->"
        comments = [{"id": 50, "body": f"{marker_html}\nold content"}]
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(comments)
            )),
        ):
            rc = mod.main([
                "--issue", "1", "--body", "new body",
                "--marker", "TEST-MARKER",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        result = json.loads(out.strip().splitlines()[-1])
        assert result["Success"] is True
        assert result["Data"]["skipped"] is True

    def test_update_when_marker_exists_and_update_flag(self, _import_module, capsys):
        mod = _import_module
        marker_html = "<!-- M -->"
        comments = [{"id": 50, "body": f"{marker_html}\nold"}]
        updated = {"id": 50, "html_url": "https://url", "updated_at": "2024-01-01"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(comments)
            )),
            patch("post_issue_comment.update_issue_comment", return_value=updated),
        ):
            rc = mod.main([
                "--issue", "1", "--body", "new body",
                "--marker", "M", "--update-if-exists",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        result = json.loads(out.strip().splitlines()[-1])
        assert result["Success"] is True
        assert result["Data"]["updated"] is True

    def test_permission_denied_exits_4(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="HTTP 403 Forbidden", returncode=1,
            )),
            patch("post_issue_comment._save_failed_comment_artifact", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 4

    def test_api_error_exits_3(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="Internal Server Error", returncode=1,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 3

    def test_post_timeout_exits_3(self, _import_module):
        # A hung gh on the POST call must surface as an external-error exit (3),
        # not block the script indefinitely (Copilot review on PR #2659).
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
                cmd=["gh"], timeout=30,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 3

    def test_marker_list_timeout_exits_3(self, _import_module):
        # A hung gh on the comments-list (marker) call must exit 3 rather than
        # wedge a CI or hook run (Copilot review on PR #2659).
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
                cmd=["gh"], timeout=30,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body", "--marker", "M"])
        assert exc.value.code == 3

    def test_json_parse_error_returns_success(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout="not json"
            )),
        ):
            rc = mod.main(["--issue", "1", "--body", "body"])
        assert rc == 0

    def test_marker_list_none_stdout_does_not_crash(self, _import_module, capsys):
        # Regression for issue #2657: on Windows the comments-list call decoded
        # gh's UTF-8 with cp1252, the stdout reader thread died on an undecodable
        # byte, and stdout came back None with returncode 0 (observed in repro).
        # Feeding None to json.loads crashed with TypeError. The marker path must
        # guard stdout and fall through to posting a new comment.
        # First mock call = list comments (None), second = POST (valid).
        # Negative control: on the pre-fix code (`if returncode == 0:` with no
        # stdout guard) the first call raises TypeError and rc is never returned.
        mod = _import_module
        response = {"id": 101, "html_url": "https://example.com/c"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                # Construct CompletedProcess directly: make_completed_process is
                # typed stdout: str, but this regression needs the genuine
                # stdout=None the Windows decode failure produces.
                subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=None, stderr=""),
                make_completed_process(stdout=json.dumps(response), returncode=0),
            ]) as mock_run,
        ):
            rc = mod.main(["--issue", "1", "--body", "b", "--marker", "M"])
        assert rc == 0
        # Prove it fell through to actually POST the comment, not just avoid a crash.
        assert mock_run.call_count == 2
        result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert result["Success"] is True
        assert result["Data"]["comment_id"] == 101
        assert result["Data"]["skipped"] is False


class TestSubprocessEncoding:
    """Lock the issue #2657 fix: every gh/git subprocess call decodes as UTF-8.

    Bare ``text=True`` decodes with the OS locale codec (cp1252 on Windows),
    which kills the reader thread on an undecodable byte (stdout -> None) or
    silently mojibakes gh's UTF-8 output. The contract is that every
    ``subprocess.run`` call in these files passes ``encoding="utf-8"`` AND
    ``errors="replace"`` (the pattern ``gh_graphql`` established).

    This parses the AST and checks each call independently, rather than scanning
    for a substring, per .claude/rules/canonical-source-mirror.md (a substring
    scan false-passes when one call is correct and another is bare, and
    false-fails on the literal appearing in a comment).
    """

    _FILES = [
        # Canonical source first: a bare text=True here is overwritten into the
        # mirrors on the next sync, so the source of truth must be validated too.
        "scripts/github_core/api.py",
        ".claude/lib/github_core/api.py",
        ".claude/skills/github/scripts/issue/post_issue_comment.py",
        # Shipped Copilot CLI mirrors: enforce the contract on what ships, not
        # just the canonical, so a desynced mirror is caught by the test itself.
        "src/copilot-cli/lib/github_core/api.py",
        "src/copilot-cli/skills/github/scripts/issue/post_issue_comment.py",
    ]

    @staticmethod
    def _kw(call, name):
        for kw in call.keywords:
            if kw.arg == name:
                return kw.value
        return None

    def _subprocess_run_calls(self, tree):
        import ast

        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                calls.append(node)
        return calls

    @pytest.mark.parametrize("rel", _FILES)
    def test_every_subprocess_run_declares_utf8(self, rel):
        import ast
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        tree = ast.parse((repo_root / rel).read_text(encoding="utf-8"))
        calls = self._subprocess_run_calls(tree)
        assert calls, f"expected subprocess.run calls in {rel}"
        for call in calls:
            encoding = self._kw(call, "encoding")
            errors = self._kw(call, "errors")
            assert (
                isinstance(encoding, ast.Constant) and encoding.value == "utf-8"
            ), f"{rel}:{call.lineno} subprocess.run missing encoding=\"utf-8\""
            assert (
                isinstance(errors, ast.Constant) and errors.value == "replace"
            ), f"{rel}:{call.lineno} subprocess.run missing errors=\"replace\""
            assert self._kw(call, "text") is None, (
                f"{rel}:{call.lineno} subprocess.run still passes text= "
                "(use encoding/errors instead)"
            )
