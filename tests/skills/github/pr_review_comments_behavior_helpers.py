"""Shared helpers for get_pr_review_comments behavior tests."""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / ".claude" / "skills" / "github" / "scripts" / "pr" / "get_pr_review_comments.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("grc_behavior_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["grc_behavior_under_test"] = module
    spec.loader.exec_module(module)
    return module


grc = _load_module()


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _review_comment(
    cid: int,
    created: str,
    *,
    author: str = "reviewer",
    author_type: str = "User",
    path: str = "src/main.py",
    line: int = 2,
    body: str = "Please adjust this",
    eyes: int = 0,
    diff_hunk: str = " context\n+print('ok')\n",
    in_reply_to: int | None = None,
):
    return {
        "id": cid,
        "user": {"login": author, "type": author_type},
        "body": body,
        "path": path,
        "line": line,
        "original_line": line,
        "side": "RIGHT",
        "diff_hunk": diff_hunk,
        "reactions": {"eyes": eyes},
        "in_reply_to_id": in_reply_to,
        "created_at": created,
        "updated_at": created,
        "html_url": "https://example.com/comment",
        "commit_id": "abc123",
    }


def _issue_comment(
    cid: int,
    created: str,
    *,
    author: str = "reviewer",
    author_type: str = "User",
    body: str = "PR-level note",
    eyes: int = 0,
):
    return {
        "id": cid,
        "user": {"login": author, "type": author_type},
        "body": body,
        "reactions": {"eyes": eyes},
        "created_at": created,
        "updated_at": created,
        "html_url": "https://example.com/issue-comment",
    }


def _stale_detection_subprocess(file_content: str):
    encoded = base64.b64encode(file_content.encode("utf-8")).decode("ascii")

    def _run(cmd, *args, **kwargs):
        endpoint = cmd[2]
        if endpoint == "repos/o/r/pulls/42":
            return _completed(stdout="abc123\n")
        if endpoint == "repos/o/r/git/trees/abc123?recursive=1":
            return _completed(
                stdout=json.dumps(
                    {"tree": [{"path": "src/main.py", "type": "blob"}]},
                ),
            )
        if endpoint.startswith("repos/o/r/contents/"):
            return _completed(stdout=json.dumps({"content": encoded}))
        raise AssertionError(f"unexpected gh api endpoint: {endpoint}")

    return _run


def _empty_tree_subprocess(cmd, *args, **kwargs):
    endpoint = cmd[2]
    if endpoint == "repos/o/r/pulls/42":
        return _completed(stdout="abc123\n")
    if endpoint == "repos/o/r/git/trees/abc123?recursive=1":
        return _completed(stdout=json.dumps({"tree": []}))
    raise AssertionError(f"unexpected gh api endpoint: {endpoint}")
