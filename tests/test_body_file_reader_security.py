"""Security cases for the body-file reader every body-file script shares (issue #6667).

PR #6908 moved ``new_pr.py`` and ``edit_pr_body.py`` onto
``github_core.validation.read_body_file_text`` and lost the owner, mode and
link checks those scripts had. Every case here runs through all five scripts
that read a body or comment file, so no reader can drift weaker than another.

The containment roots are pinned to directories under ``tmp_path``: a fake
repo, and a world-writable fake ``/tmp``. Where the runner keeps its own temp
dir then cannot change a verdict.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.github_core.repo import REPO_ROOT_OK
from tests.containment_fixtures import _github_core_modules

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getuid"),
    reason="owner and mode bits are POSIX only",
)

_SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts"
_BODY = "## Summary\n\nbody under test\n"
_ATTACKER = "attacker text\n"


def _load(relative: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, _SKILL_SCRIPTS / relative)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


_NEW_PR = _load("pr/new_pr.py", "body_reader_security_new_pr")
_NEW_PR._load_body_file_reader()
_EDIT_PR_BODY = _load("pr/edit_pr_body.py", "body_reader_security_edit_pr_body")
_CLOSE_ISSUE = _load("issue/close_issue.py", "body_reader_security_close_issue")
_REOPEN_ISSUE = _load("issue/reopen_issue.py", "body_reader_security_reopen_issue")
_POST_ISSUE_COMMENT = _load("issue/post_issue_comment.py", "body_reader_security_post_comment")


class RefusedError(Exception):
    """The script refused the body file."""


class _CapturedError(Exception):
    def __init__(self, body: str) -> None:
        super().__init__("captured")
        self.body = body


def _read_with_new_pr(path: Path, repo: Path) -> str:
    args = argparse.Namespace(title="feat: body", body="", body_file=str(path))
    body = _NEW_PR._read_body(args, str(repo))
    if body is None:
        raise RefusedError("new_pr.py")
    return body


def _read_with_edit_pr_body(path: Path, _repo: Path) -> str:
    body, error = _EDIT_PR_BODY._read_new_body(argparse.Namespace(body=None, body_file=str(path)))
    if error:
        raise RefusedError(error)
    return body


def _read_with_issue_script(module) -> Callable[[Path, Path], str]:
    def _read(path: Path, _repo: Path) -> str:
        try:
            return module._resolve_comment("", str(path), "json")
        except SystemExit as exc:
            raise RefusedError(module.__name__) from exc

    return _read


def _read_with_post_issue_comment(path: Path, _repo: Path) -> str:
    module = _POST_ISSUE_COMMENT

    def _capture(body: str) -> None:
        raise _CapturedError(body)

    patches = {
        "assert_gh_authenticated": lambda: None,
        "resolve_repo_params": lambda _owner, _repo: SimpleNamespace(owner="o", repo="r"),
        "inline_body_error": _capture,
    }
    saved = {name: getattr(module, name) for name in patches}
    for name, value in patches.items():
        setattr(module, name, value)
    try:
        module.main(["--issue", "1", "--body-file", str(path)])
    except _CapturedError as captured:
        return captured.body
    except SystemExit as exc:
        raise RefusedError("post_issue_comment.py") from exc
    finally:
        for name, value in saved.items():
            setattr(module, name, value)
    raise AssertionError("post_issue_comment.py never reached the body check")


READERS: dict[str, Callable[[Path, Path], str]] = {
    "new_pr": _read_with_new_pr,
    "edit_pr_body": _read_with_edit_pr_body,
    "close_issue": _read_with_issue_script(_CLOSE_ISSUE),
    "reopen_issue": _read_with_issue_script(_REOPEN_ISSUE),
    "post_issue_comment": _read_with_post_issue_comment,
}


@dataclass
class Area:
    """The pinned roots: a fake repo and a world-writable fake ``/tmp``."""

    repo: Path
    tmp: Path
    monkeypatch: pytest.MonkeyPatch

    def set_temp_roots(self, *roots: Path) -> None:
        resolved = [str(root.resolve()) for root in roots]
        for module in _github_core_modules("validation"):
            self.monkeypatch.setattr(module, "_candidate_temp_roots", lambda: list(resolved))

    def set_git_dirs(self, *dirs: Path) -> None:
        resolved = [str(directory.resolve()) for directory in dirs]
        for module in _github_core_modules("validation"):
            self.monkeypatch.setattr(module, "_candidate_git_dir_roots", lambda: list(resolved))


def _mkdir(path: Path, mode: int) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    return path


def _write(path: Path, mode: int, text: str = _BODY) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def build_area(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Area:
    """Pin the roots under ``tmp_path``. Other body-file suites reuse this."""
    base = _mkdir(tmp_path.resolve() / "area", 0o700)
    repo = _mkdir(base / "repo", 0o755)
    fake_tmp = _mkdir(base / "tmp", 0o1777)
    for module in _github_core_modules("repo"):
        monkeypatch.setattr(module, "resolve_repo_root", lambda **_kwargs: (repo, REPO_ROOT_OK))
    built = Area(repo=repo, tmp=fake_tmp, monkeypatch=monkeypatch)
    built.set_temp_roots(fake_tmp)
    built.set_git_dirs()
    monkeypatch.chdir(repo)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    return built


@pytest.fixture
def area(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Area:
    return build_area(tmp_path, monkeypatch)


# Positive cases ------------------------------------------------------------


def _owned_600(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / "body.md", 0o600)


def _owned_664_in_owner_only_dir(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / "body.md", 0o664)


def _session_scratchpad(area: Area) -> Path:
    # The Claude Code layout: /tmp/claude-<uid>/<project>/<session>/scratchpad,
    # every level mode 700. Mode 664 is what the Write tool leaves under umask 002.
    scratchpad = area.tmp
    for name in ("claude-1000", "-home-user-src-repo", "session-id", "scratchpad"):
        scratchpad = _mkdir(scratchpad / name, 0o700)
    return _write(scratchpad / "body.md", 0o664)


def _prepared_body_in_repo_scratch(area: Area) -> Path:
    scratch = _mkdir(_mkdir(area.repo / ".project-toolkit", 0o700) / "scratch", 0o700)
    return _write(scratch / "pr-body-0123abcd.md", 0o600)


def _plain_pr_body_name(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / "pr-body.md", 0o600)


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    "make_body",
    [
        _owned_600,
        _owned_664_in_owner_only_dir,
        _session_scratchpad,
        _prepared_body_in_repo_scratch,
        _plain_pr_body_name,
    ],
    ids=[
        "owned-600",
        "owned-664-owner-only-dir",
        "session-scratchpad",
        "prepared-body",
        "plain-pr-body-name",
    ],
)
def test_accepts_private_body_file(
    area: Area, script: str, make_body: Callable[[Area], Path]
) -> None:
    body = make_body(area)
    assert READERS[script](body, area.repo) == _BODY


# Negative cases ------------------------------------------------------------


def _foreign_owner(area: Area) -> Path:
    body = _owned_600(area)
    real_getuid = os.getuid
    area.monkeypatch.setattr(os, "getuid", lambda: real_getuid() + 1)
    return body


def _world_writable(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / "body.md", 0o646)


def _group_writable_in_group_writable_dir(area: Area) -> Path:
    return _write(_mkdir(area.repo / "drafts", 0o775) / "body.md", 0o664)


def _group_writable_without_owner_only_dir(area: Area) -> Path:
    # No group write on any directory, but every one lets the group search, so
    # a group member could open the 664 file and rewrite it.
    return _write(_mkdir(area.repo / "drafts", 0o755) / "body.md", 0o664)


def _hard_link(area: Area) -> Path:
    body = _owned_600(area)
    (body.parent / "second-name.md").hardlink_to(body)
    return body


def _symlinked_file(area: Area) -> Path:
    private = _mkdir(area.tmp / "private", 0o700)
    target = _write(private / "real.md", 0o600)
    link = private / "body.md"
    link.symlink_to(target)
    return link


def _parent_swapped_after_check(area: Area) -> Path:
    private = _mkdir(area.tmp / "private", 0o700)
    real_parent = _mkdir(private / "sub", 0o700)
    body = _write(real_parent / "body.md", 0o600)
    attacker_dir = _mkdir(private / "elsewhere", 0o700)
    _write(attacker_dir / "body.md", 0o600, _ATTACKER)
    real_open = os.open
    swapped = False

    def _swap_then_open(target, flags, *args, **kwargs):
        # The reader's first open, of the filesystem root or of a path under
        # the fake /tmp, comes after the path was resolved and checked. Swap
        # the parent for a symlink right before it.
        nonlocal swapped
        first_open = str(target) == os.sep or str(target).startswith(str(area.tmp))
        if not swapped and first_open:
            swapped = True
            real_parent.rename(private / "sub-moved")
            (private / "sub").symlink_to(attacker_dir, target_is_directory=True)
        return real_open(target, flags, *args, **kwargs)

    area.monkeypatch.setattr(os, "open", _swap_then_open)
    return body


def _nested_tmpdir_under_world_writable_tmp(area: Area) -> Path:
    # TMPDIR is a world-writable directory inside the fake /tmp. Both are temp
    # roots, TMPDIR listed first, as _candidate_temp_roots lists it.
    nested = _mkdir(area.tmp / "shared-tmpdir", 0o777)
    area.set_temp_roots(nested, area.tmp)
    return _write(_mkdir(nested / "private", 0o700) / "body.md", 0o600)


def _git_config(area: Area) -> Path:
    git_dir = _mkdir(area.repo / ".git", 0o700)
    area.set_git_dirs(git_dir)
    return _write(git_dir / "config", 0o600, "[remote]\n\turl = https://token@example\n")


def _repo_dotfile(area: Area) -> Path:
    return _write(area.repo / ".env", 0o600, "TOKEN=secret\n")


def _nested_repo_dotfile(area: Area) -> Path:
    return _write(_mkdir(area.repo / "service", 0o755) / ".env", 0o600, "TOKEN=secret\n")


def _dotfile_under_temp_root(area: Area) -> Path:
    clone_git = _mkdir(area.tmp / "private" / "other-clone" / ".git", 0o700)
    area.tmp.joinpath("private", "other-clone").chmod(0o700)
    area.tmp.joinpath("private").chmod(0o700)
    return _write(clone_git / "config", 0o600, "[remote]\n\turl = https://token@example\n")


def _temp_root_without_sticky_bit(area: Area) -> Path:
    # A world-writable TMPDIR without the sticky bit lets another user rename
    # the caller's entries in it.
    shared = _mkdir(area.repo.parent / "shared", 0o777)
    area.set_temp_roots(shared)
    return _write(_mkdir(shared / "private", 0o700) / "body.md", 0o600)


def _ntfs_short_name_dir(area: Area) -> Path:
    # GIT~1 is the 8.3 short name NTFS gives .git.
    return _write(_mkdir(area.repo / "GIT~1", 0o700) / "config", 0o600)


def _trailing_dot(area: Area) -> Path:
    # NTFS drops a trailing dot, so "config." opens "config".
    return _write(_mkdir(area.tmp / "private", 0o700) / "config.", 0o600)


def _trailing_space_dotfile(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / ".env ", 0o600)


def _alternate_data_stream(area: Area) -> Path:
    return _write(_mkdir(area.tmp / "private", 0o700) / "notes.md:evil", 0o600)


def _prepared_body_not_600(area: Area) -> Path:
    scratch = _mkdir(_mkdir(area.repo / ".project-toolkit", 0o700) / "scratch", 0o700)
    return _write(scratch / "pr-body-0123abcd.md", 0o640)


_NEGATIVE_CASES = {
    "foreign-owner": _foreign_owner,
    "world-writable-file": _world_writable,
    "664-in-group-writable-dir": _group_writable_in_group_writable_dir,
    "664-without-owner-only-dir": _group_writable_without_owner_only_dir,
    "hard-link": _hard_link,
    "symlinked-file": _symlinked_file,
    "parent-swapped-after-check": _parent_swapped_after_check,
    "nested-tmpdir-under-world-writable-tmp": _nested_tmpdir_under_world_writable_tmp,
    "git-config": _git_config,
    "repo-dotfile": _repo_dotfile,
    "nested-repo-dotfile": _nested_repo_dotfile,
    "dotfile-under-temp-root": _dotfile_under_temp_root,
    "temp-root-without-sticky-bit": _temp_root_without_sticky_bit,
    "ntfs-short-name-dir": _ntfs_short_name_dir,
    "trailing-dot": _trailing_dot,
    "trailing-space-dotfile": _trailing_space_dotfile,
    "alternate-data-stream": _alternate_data_stream,
    "prepared-body-not-600": _prepared_body_not_600,
}


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("case", sorted(_NEGATIVE_CASES))
def test_refuses_unsafe_body_file(area: Area, script: str, case: str) -> None:
    body = _NEGATIVE_CASES[case](area)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


# Git-dir reply flow ----------------------------------------------------------


def _linked_worktree_git_dir(area: Area) -> Path:
    common = _mkdir(area.tmp / "private" / "main-clone.git", 0o700)
    git_dir = _mkdir(common / "worktrees" / "feature", 0o700)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    area.set_git_dirs(git_dir)
    return git_dir


@pytest.mark.parametrize("script", ["close_issue", "reopen_issue", "post_issue_comment"])
def test_issue_scripts_keep_linked_worktree_git_dir_flow(area: Area, script: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / "reply.md", 0o600)
    area.set_temp_roots()
    assert READERS[script](body, area.repo) == _BODY


@pytest.mark.parametrize("script", ["new_pr", "edit_pr_body"])
def test_pr_scripts_refuse_the_git_dir(area: Area, script: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / "reply.md", 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_linked_worktree_git_config(area: Area, script: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / "config.worktree", 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("name", ["CONFIG.worktree", "Config"])
def test_refuses_git_config_in_any_case(area: Area, script: str, name: str) -> None:
    body = _write(_linked_worktree_git_dir(area) / name, 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_common_git_dir_config_beside_linked_worktree(area: Area, script: str) -> None:
    common = _linked_worktree_git_dir(area).parents[1]
    body = _write(common / "config", 0o600, "[remote]\n\turl = https://token@example\n")
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


@pytest.mark.parametrize(
    ("make_body", "accepted"),
    [(_owned_600, True), (_symlinked_file, False), (_parent_swapped_after_check, False)],
    ids=["owned-600", "symlinked-file", "parent-swapped-after-check"],
)
def test_path_fallback_without_dir_fd(
    area: Area, make_body: Callable[[Area], Path], accepted: bool
) -> None:
    """The Windows branch, which has no dir_fd, runs here by forcing it off."""
    for module in _github_core_modules("body_file"):
        area.monkeypatch.setattr(module, "_HAS_DIR_FD", False)
    body = make_body(area)
    if accepted:
        assert READERS["new_pr"](body, area.repo) == _BODY
    else:
        with pytest.raises(RefusedError):
            READERS["new_pr"](body, area.repo)


def _as_windows(area: Area, final: Callable[[Path], Path | None]) -> None:
    """Take the Windows branch that rechecks the opened file's real name."""
    for module in _github_core_modules("body_file"):
        area.monkeypatch.setattr(module, "_IS_WINDOWS", True)
        area.monkeypatch.setattr(module, "_final_path", final)


@pytest.mark.parametrize(
    ("real_name", "accepted"),
    [
        (lambda body, _area: body, True),
        (lambda _body, area: area.repo / ".git" / "config", False),
        (lambda body, _area: body.parent / ".env", False),
        (lambda _body, area: area.repo.parent / "outside.md", False),
        (lambda _body, _area: None, False),
    ],
    ids=["same-name", "real-name-is-git-config", "real-name-is-dotfile", "outside-root", "unknown"],
)
def test_windows_rechecks_the_real_name(
    area: Area, real_name: Callable[[Path, Area], Path | None], accepted: bool
) -> None:
    """GetFinalPathNameByHandle expands GIT~1 and drops trailing dots; recheck its answer."""
    # Under the repo, so a real name of .git/config reaches the git checks
    # instead of failing the outside-root check first.
    body = _write(_mkdir(area.repo / "drafts", 0o700) / "body.md", 0o600)
    _as_windows(area, lambda _descriptor: real_name(body, area))
    if accepted:
        assert READERS["new_pr"](body, area.repo) == _BODY
    else:
        with pytest.raises(RefusedError):
            READERS["new_pr"](body, area.repo)
