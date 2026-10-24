"""Directory owner and mode checks outside temp roots (issue #6918).

Below a temp root every directory must already be private. Below the repo
root or the git dir, the reader now refuses a directory another user owns and
one anyone can write without the sticky bit. Group write stays allowed there,
since umask 002 leaves every repo directory at mode 775.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.github_core.repo import REPO_ROOT_OK
from tests.containment_fixtures import _github_core_modules
from tests.test_body_file_reader_security import _BODY, READERS, RefusedError

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getuid"),
    reason="owner and mode bits are POSIX only",
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A mode 775 fake repo as the only approved root."""
    base = tmp_path.resolve() / "area"
    base.mkdir()
    base.chmod(0o700)
    root = base / "repo"
    root.mkdir()
    root.chmod(0o775)
    for module in _github_core_modules("repo"):
        monkeypatch.setattr(module, "resolve_repo_root", lambda **_kwargs: (root, REPO_ROOT_OK))
    _set_roots(monkeypatch, temp=[], git=[])
    monkeypatch.chdir(root)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    return root


def _set_roots(monkeypatch: pytest.MonkeyPatch, *, temp: list[Path], git: list[Path]) -> None:
    temp_roots = [str(path.resolve()) for path in temp]
    git_roots = [str(path.resolve()) for path in git]
    for module in _github_core_modules("validation"):
        monkeypatch.setattr(module, "_candidate_temp_roots", lambda: list(temp_roots))
        monkeypatch.setattr(module, "_candidate_git_dir_roots", lambda: list(git_roots))


def _dir(path: Path, mode: int) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    return path


def _body(directory: Path) -> Path:
    path = directory / "body.md"
    path.write_text(_BODY, encoding="utf-8")
    path.chmod(0o600)
    return path


def _directories_owned_by(monkeypatch: pytest.MonkeyPatch, uid: int, below: Path) -> None:
    """Report ``uid`` as the owner of every directory at or below ``below``."""
    real_fstat = os.fstat
    real_open = os.open
    names: dict[int, Path] = {}

    def _open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        parent = names.get(dir_fd) if dir_fd is not None else None
        names[descriptor] = Path(parent / path) if parent is not None else Path(path)
        return descriptor

    def _fstat(descriptor: int):
        result = real_fstat(descriptor)
        name = names.get(descriptor)
        inside = name is not None and (name == below or below in name.parents)
        if stat.S_ISDIR(result.st_mode) and inside:
            fields = list(result)
            fields[4] = uid  # st_uid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "fstat", _fstat)


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    "mode",
    [0o775, 0o755, 0o700, 0o1777],
    ids=["group-writable-775", "755", "owner-only", "world-writable-sticky"],
)
def test_accepts_repo_directory_modes(repo: Path, script: str, mode: int) -> None:
    body = _body(_dir(repo / "drafts", mode))
    assert READERS[script](body, repo) == _BODY


@pytest.mark.parametrize("script", sorted(READERS))
def test_accepts_root_owned_repo_directory(
    repo: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = _dir(repo / "drafts", 0o755)
    body = _body(drafts)
    _directories_owned_by(monkeypatch, 0, drafts)
    assert READERS[script](body, repo) == _BODY


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("depth", ["repo-root", "nested"])
def test_refuses_world_writable_directory_without_sticky_bit(
    repo: Path, script: str, depth: str
) -> None:
    drafts = _dir(repo / "drafts" / "inner", 0o755)
    if depth == "repo-root":
        repo.chmod(0o777)
    else:
        (repo / "drafts").chmod(0o777)
    body = _body(drafts)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("target", ["repo-root", "nested"])
def test_refuses_directory_another_user_owns(
    repo: Path, script: str, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = _dir(repo / "drafts", 0o755)
    body = _body(drafts)
    _directories_owned_by(monkeypatch, os.getuid() + 1, repo if target == "repo-root" else drafts)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("script", ["close_issue", "reopen_issue", "post_issue_comment"])
def test_refuses_world_writable_linked_worktree_git_dir(
    repo: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    common = _dir(repo.parent / "clone.git", 0o700)
    git_dir = _dir(common / "worktrees" / "feature", 0o700)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    _set_roots(monkeypatch, temp=[], git=[git_dir])
    body = _body(git_dir)
    assert READERS[script](body, repo) == _BODY
    git_dir.chmod(0o777)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_world_writable_directory_above_a_nested_temp_root(
    repo: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A TMPDIR inside the repo: the repo directories above it are checked too."""
    shared = _dir(repo / "shared", 0o755)
    temp = _dir(shared / "tmp", 0o700)
    _set_roots(monkeypatch, temp=[temp], git=[])
    body = _body(_dir(temp / "private", 0o700))
    assert READERS[script](body, repo) == _BODY
    shared.chmod(0o777)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("script", ["close_issue", "reopen_issue", "post_issue_comment"])
def test_refuses_world_writable_worktrees_dir_above_the_git_dir(
    repo: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The walk starts at the common git dir, so ``.git/worktrees`` is checked."""
    common = _dir(repo.parent / "clone.git", 0o700)
    worktrees = _dir(common / "worktrees", 0o700)
    git_dir = _dir(worktrees / "feature", 0o700)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    _set_roots(monkeypatch, temp=[], git=[git_dir])
    body = _body(git_dir)
    assert READERS[script](body, repo) == _BODY
    worktrees.chmod(0o777)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_root_owned_world_writable_directory_without_sticky_bit(
    repo: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = _dir(repo / "drafts", 0o777)
    body = _body(drafts)
    _directories_owned_by(monkeypatch, 0, drafts)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


@pytest.mark.parametrize("case", ["world-writable", "foreign-owner"])
def test_path_fallback_without_dir_fd_refuses_too(
    repo: Path, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows-style path walk, forced on POSIX, runs the same directory checks."""
    for module in _github_core_modules("body_file"):
        monkeypatch.setattr(module, "_HAS_DIR_FD", False)
    drafts = _dir(repo / "drafts", 0o755)
    body = _body(drafts)
    assert READERS["new_pr"](body, repo) == _BODY
    if case == "world-writable":
        drafts.chmod(0o777)
    else:
        real_lstat = Path.lstat

        def _lstat(self: Path):
            result = real_lstat(self)
            if self == drafts:
                fields = list(result)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return result

        monkeypatch.setattr(Path, "lstat", _lstat)
    with pytest.raises(RefusedError):
        READERS["new_pr"](body, repo)
