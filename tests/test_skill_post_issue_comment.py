"""Tests for post_issue_comment.py skill script (issue/ directory)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str, module_alias: str = ""):
    alias = module_alias or name
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("post_issue_comment", "skill_post_issue_comment")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_post_comment(mock_run, capsys):
    response = json.dumps({
        "id": 100,
        "html_url": "https://github.com/o/r/issues/1#issuecomment-100",
        "created_at": "2025-01-01T00:00:00Z",
    })
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=response),  # post comment
    ]

    rc = main(["--issue", "1", "--body", "Hello"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["comment_id"] == 100


@patch("subprocess.run")
def test_empty_body_fails(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--body", ""])
    assert exc_info.value.code == 2


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from text that may contain plain text lines."""
    lines = text.strip().splitlines()
    # Walk backwards to find start of JSON block
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("{"):
            result: dict = json.loads("\n".join(lines[i:]))
            return result
    raise ValueError(f"No JSON object found in: {text!r}")


@patch("subprocess.run")
def test_marker_skip_existing(mock_run, capsys):
    comments = json.dumps([
        {"id": 50, "body": "<!-- TEST-MARKER -->\n\nOld content", "user": {"login": "bot"}}
    ])
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=comments),  # get comments
    ]

    rc = main(["--issue", "1", "--body", "New content", "--marker", "TEST-MARKER"])
    assert rc == 0
    output = _extract_json(capsys.readouterr().out)
    assert output["skipped"] is True


@patch("subprocess.run")
def test_marker_update_existing(mock_run, capsys):
    comments = json.dumps([
        {"id": 50, "body": "<!-- TEST-MARKER -->\n\nOld", "user": {"login": "bot"}}
    ])
    updated = json.dumps({
        "id": 50,
        "html_url": "https://github.com/o/r/issues/1#issuecomment-50",
        "updated_at": "2025-01-02T00:00:00Z",
    })
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=comments),  # get comments
        _completed(stdout=updated),  # update comment
    ]

    rc = main([
        "--issue", "1", "--body", "Updated",
        "--marker", "TEST-MARKER", "--update-if-exists",
    ])
    assert rc == 0
    output = _extract_json(capsys.readouterr().out)
    assert output["updated"] is True


@patch("subprocess.run")
def test_403_error(mock_run, tmp_path):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1, stderr="HTTP 403: Resource not accessible by integration"),  # post fails
        _completed(stdout=str(tmp_path)),  # git rev-parse --show-toplevel
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--body", "test"])
    assert exc_info.value.code == 4


@patch("subprocess.run")
def test_body_file(mock_run, capsys, tmp_path):
    body_file = tmp_path / "comment.md"
    body_file.write_text("File comment body")

    response = json.dumps({"id": 200, "html_url": "url", "created_at": "now"})
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=response),
    ]

    rc = main(["--issue", "1", "--body-file", str(body_file)])
    assert rc == 0
