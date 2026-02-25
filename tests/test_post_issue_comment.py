"""Tests for post_issue_comment.py consumer script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("post_issue_comment")
main = _mod.main
build_parser = _mod.build_parser
save_failed_comment_artifact = _mod.save_failed_comment_artifact
_prepend_marker = _mod._prepend_marker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _setup_output(tmp_path: Path, monkeypatch) -> Path:
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _read_outputs(output_file: Path) -> dict[str, str]:
    lines = output_file.read_text().strip().splitlines()
    result = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def _mock_authenticated():
    return patch("subprocess.run", return_value=_completed(rc=0))


# ---------------------------------------------------------------------------
# Tests: _prepend_marker
# ---------------------------------------------------------------------------


class TestPrependMarker:
    def test_adds_marker(self):
        result = _prepend_marker("body text", "<!-- marker -->")
        assert result.startswith("<!-- marker -->")
        assert "body text" in result

    def test_does_not_duplicate_marker(self):
        body = "<!-- marker -->\n\nbody text"
        result = _prepend_marker(body, "<!-- marker -->")
        assert result == body


# ---------------------------------------------------------------------------
# Tests: save_failed_comment_artifact
# ---------------------------------------------------------------------------


class TestSaveFailedCommentArtifact:
    def test_saves_artifact(self, tmp_path):
        with patch("subprocess.run", return_value=_completed(
            stdout=str(tmp_path), rc=0,
        )):
            path = save_failed_comment_artifact("o", "r", 1, "body", "error")
        assert path is not None
        content = json.loads(Path(path).read_text())
        assert content["owner"] == "o"
        assert content["issue"] == 1

    def test_returns_none_on_write_failure(self, tmp_path):
        with patch("subprocess.run", return_value=_completed(
            stdout="/nonexistent/path", rc=0,
        )), patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
            path = save_failed_comment_artifact("o", "r", 1, "body", "error")
        assert path is None


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--issue", "1",
                "--body", "text",
                "--body-file", "file.md",
            ])

    def test_valid_args(self):
        args = build_parser().parse_args(["--issue", "42", "--body", "hello"])
        assert args.issue == 42
        assert args.body == "hello"


# ---------------------------------------------------------------------------
# Tests: main - auth
# ---------------------------------------------------------------------------


class TestMainAuth:
    def test_exits_4_when_not_authenticated(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=1)):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body", "test"])
            assert exc.value.code == 4


# ---------------------------------------------------------------------------
# Tests: main - body resolution
# ---------------------------------------------------------------------------


class TestMainBody:
    def test_empty_body_exits_1(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body", ""])
            assert exc.value.code == 1

    def test_body_from_file(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        body_file = tmp_path / "body.md"
        body_file.write_text("hello from file")
        response = json.dumps({"id": 1, "html_url": "https://example.com", "created_at": "now"})
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _completed(rc=0, stdout=response)

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--issue", "1", "--body-file", str(body_file)])
        assert rc == 0

    def test_body_file_not_found_exits_2(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body-file", "/nonexistent/body.md"])
            assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: main - idempotency
# ---------------------------------------------------------------------------


class TestMainIdempotency:
    def test_marker_skip_when_exists(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        existing_comments = [{"id": 99, "body": "<!-- test-marker -->\nold body"}]

        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "post_issue_comment.get_issue_comments",
            return_value=existing_comments,
        ):
            rc = main([
                "--issue", "1",
                "--body", "new body",
                "--marker", "test-marker",
            ])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["skipped"] == "true"

    def test_marker_update_when_exists_and_update_flag(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        existing_comments = [{"id": 99, "body": "<!-- test-marker -->\nold body"}]
        update_response = {"id": 99, "html_url": "https://ex.com", "updated_at": "now"}

        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "post_issue_comment.get_issue_comments",
            return_value=existing_comments,
        ), patch(
            "post_issue_comment.update_issue_comment",
            return_value=update_response,
        ):
            rc = main([
                "--issue", "1",
                "--body", "updated body",
                "--marker", "test-marker",
                "--update-if-exists",
            ])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["updated"] == "true"

    def test_marker_not_found_posts_new(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        response = json.dumps({
            "id": 1, "html_url": "https://ex.com", "created_at": "now",
        })

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _completed(rc=0, stdout=response)

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "post_issue_comment.get_issue_comments",
            return_value=[],
        ):
            rc = main([
                "--issue", "1",
                "--body", "new comment",
                "--marker", "new-marker",
            ])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["skipped"] == "false"


# ---------------------------------------------------------------------------
# Tests: main - post errors
# ---------------------------------------------------------------------------


class TestMainPostErrors:
    def test_403_exits_4(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        # First call: auth check (success). Second call: post (403 failure).
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(rc=0)  # auth
            return _completed(rc=1, stderr="HTTP 403: Forbidden")

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body", "test body"])
            assert exc.value.code == 4

    def test_api_error_exits_3(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(rc=0)  # auth
            return _completed(rc=1, stderr="HTTP 500: Internal Server Error")

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body", "test body"])
            assert exc.value.code == 3

    def test_timeout_exits_3(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(rc=0)  # auth
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--body", "test body"])
            assert exc.value.code == 3

    def test_invalid_json_response_still_succeeds(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(rc=0)  # auth
            return _completed(rc=0, stdout="not json")

        with patch("subprocess.run", side_effect=_side_effect), patch(
            "post_issue_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--issue", "1", "--body", "test body"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["parse_error"] == "true"
