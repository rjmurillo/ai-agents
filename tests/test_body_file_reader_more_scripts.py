"""The strict body-file reader on the six scripts that used containment only (issue #6919).

``new_issue.py``, ``edit_issue_body.py``, ``close_pr.py`` and the three PR
reply scripts checked the path, then opened it by name. They now read through
``read_body_file_text``. Every positive and negative case from
``test_body_file_reader_security`` runs through each of them here.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_body_file_reader_security import (
    _BODY,
    _NEGATIVE_CASES,
    Area,
    RefusedError,
    _as_windows,
    _linked_worktree_git_dir,
    _load,
    _mkdir,
    _owned_600,
    _owned_664_in_owner_only_dir,
    _prepared_body_in_repo_scratch,
    _session_scratchpad,
    _write,
    build_area,
)

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getuid"),
    reason="owner and mode bits are POSIX only",
)

_NEW_ISSUE = _load("issue/new_issue.py", "body_reader_more_new_issue")
_EDIT_ISSUE_BODY = _load("issue/edit_issue_body.py", "body_reader_more_edit_issue_body")
_CLOSE_PR = _load("pr/close_pr.py", "body_reader_more_close_pr")
_THREAD_REPLY = _load("pr/add_pr_review_thread_reply.py", "body_reader_more_thread_reply")
_COMMENT_REPLY = _load("pr/post_pr_comment_reply.py", "body_reader_more_comment_reply")
_REVIEW_COMMENT = _load("pr/new_pr_review_comment.py", "body_reader_more_review_comment")


class _CapturedError(Exception):
    def __init__(self, body: str) -> None:
        super().__init__("captured")
        self.body = body


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def area(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Area:
    built = build_area(tmp_path, monkeypatch)
    repo_info = SimpleNamespace(owner="o", repo="r")
    for module in (_EDIT_ISSUE_BODY, _CLOSE_PR):
        monkeypatch.setattr(module, "resolve_repo_params", lambda _owner, _repo: repo_info)
    monkeypatch.setattr(_CLOSE_PR, "assert_gh_authenticated", lambda: None)
    return built


def _refusing(call: Callable[[], str], name: str) -> str:
    try:
        return call()
    except SystemExit as exc:
        raise RefusedError(name) from exc


def _read_with_new_issue(path: Path, _area: Area) -> str:
    body = _NEW_ISSUE._read_body(argparse.Namespace(body="", body_file=str(path)), "json")
    if isinstance(body, int):
        raise RefusedError("new_issue.py")
    return body


def _read_with_edit_issue_body(path: Path, area: Area) -> str:
    def _fake_run(args, **kwargs):
        assert str(path) not in args, "gh must not reopen the body path"
        raise _CapturedError(kwargs.get("input"))

    area.monkeypatch.setattr(subprocess, "run", _fake_run)
    try:
        _refusing(
            lambda: _EDIT_ISSUE_BODY.main(["--issue", "1", "--body-file", str(path)]),
            "edit_issue_body.py",
        )
    except _CapturedError as captured:
        return captured.body
    raise AssertionError("edit_issue_body.py never reached gh")


def _read_with_close_pr(path: Path, area: Area) -> str:
    def _fake_run(args, **_kwargs):
        if "comment" in args:
            raise _CapturedError(args[args.index("--body") + 1])
        return _completed(json.dumps({"state": "OPEN"}))

    area.monkeypatch.setattr(subprocess, "run", _fake_run)
    try:
        _refusing(
            lambda: _CLOSE_PR.main(["--pull-request", "1", "--comment-file", str(path)]),
            "close_pr.py",
        )
    except _CapturedError as captured:
        return captured.body
    raise AssertionError("close_pr.py never posted the comment")


def _resolve_body_reader(module, name: str) -> Callable[[Path, Area], str]:
    def _read(path: Path, _area: Area) -> str:
        args = argparse.Namespace(body=None, body_file=str(path))
        return _refusing(lambda: module._resolve_body(args), name)

    return _read


READERS: dict[str, Callable[[Path, Area], str]] = {
    "new_issue": _read_with_new_issue,
    "edit_issue_body": _read_with_edit_issue_body,
    "close_pr": _read_with_close_pr,
    "add_pr_review_thread_reply": _resolve_body_reader(_THREAD_REPLY, "thread reply"),
    "post_pr_comment_reply": _resolve_body_reader(_COMMENT_REPLY, "comment reply"),
    "new_pr_review_comment": _resolve_body_reader(_REVIEW_COMMENT, "review comment"),
}


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    "make_body",
    [_owned_600, _owned_664_in_owner_only_dir, _session_scratchpad, _prepared_body_in_repo_scratch],
    ids=["owned-600", "owned-664-owner-only-dir", "session-scratchpad", "prepared-body"],
)
def test_accepts_private_body_file(
    area: Area, script: str, make_body: Callable[[Area], Path]
) -> None:
    assert READERS[script](make_body(area), area) == _BODY


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("case", sorted(_NEGATIVE_CASES))
def test_refuses_unsafe_body_file(area: Area, script: str, case: str) -> None:
    body = _NEGATIVE_CASES[case](area)
    with pytest.raises(RefusedError):
        READERS[script](body, area)


@pytest.mark.parametrize("script", sorted(READERS))
def test_keeps_linked_worktree_git_dir_reply_flow(area: Area, script: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / "reply.md", 0o600)
    area.set_temp_roots()
    assert READERS[script](body, area) == _BODY


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("name", ["config", "config.worktree"])
def test_refuses_linked_worktree_git_config(area: Area, script: str, name: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / name, 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area)


@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_primary_clone_git_dir(area: Area, script: str) -> None:
    """Containment once accepted any file in the git dir; a primary clone's never qualifies."""
    git_dir = area.repo / ".git"
    git_dir.mkdir(mode=0o700)
    area.set_git_dirs(git_dir)
    body = _write(git_dir / "reply.md", 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area)


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    ("real_name", "accepted"),
    [
        (lambda body, _area: body, True),
        (lambda body, _area: body.parent / ".env", False),
        (lambda _body, area: area.repo / ".git" / "config", False),
    ],
    ids=["same-name", "real-name-is-dotfile", "real-name-is-git-config"],
)
def test_windows_real_name_recheck_runs_for_each_script(
    area: Area, script: str, real_name, accepted: bool
) -> None:
    """The Windows branch, forced on POSIX, rechecks the opened file's real name."""
    body = _write(_mkdir(area.repo / "drafts", 0o700) / "body.md", 0o600)
    _as_windows(area, lambda _descriptor: real_name(body, area))
    if accepted:
        assert READERS[script](body, area) == _BODY
    else:
        with pytest.raises(RefusedError):
            READERS[script](body, area)


def test_edit_issue_body_inline_body_sends_no_stdin(area: Area) -> None:
    calls: list[tuple[list[str], object]] = []

    def _fake_run(args, **kwargs):
        calls.append((list(args), kwargs.get("input")))
        return _completed()

    area.monkeypatch.setattr(subprocess, "run", _fake_run)
    assert _EDIT_ISSUE_BODY.main(["--issue", "1", "--body", "inline text"]) == 0
    ((args, stdin),) = calls
    assert stdin is None
    assert "-" not in args
    assert args[args.index("--body") + 1] == "inline text"


def test_edit_issue_body_pipes_stdin_as_utf8(area: Area) -> None:
    body = _write(_mkdir(area.tmp / "private", 0o700) / "body.md", 0o600, "caf\u00e9 \u2713\n")
    seen: list[dict] = []

    def _fake_run(args, **kwargs):
        seen.append(kwargs)
        return _completed()

    area.monkeypatch.setattr(subprocess, "run", _fake_run)
    assert _EDIT_ISSUE_BODY.main(["--issue", "1", "--body-file", str(body)]) == 0
    (kwargs,) = seen
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["input"] == "caf\u00e9 \u2713\n"
