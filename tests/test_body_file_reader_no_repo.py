"""No-repo and pseudo-filesystem cases for the shared body-file reader (issue #6916).

Outside a git repo the working directory used to be an approved root, so with
a system directory as the working directory any caller-owned file passed,
including kernel pseudo-files that expose the environment. These cases run
through every strict reader in ``test_body_file_reader_security`` and through
the containment rule the other body-file scripts use.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.github_core.repo import REPO_ROOT_GIT_FAILED, REPO_ROOT_NOT_A_REPO, REPO_ROOT_OK
from tests.containment_fixtures import _github_core_modules
from tests.test_body_file_reader_security import (
    _BODY,
    READERS,
    Area,
    RefusedError,
    _mkdir,
    _owned_600,
    _write,
    build_area,
)

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getuid"),
    reason="owner and mode bits are POSIX only",
)


@pytest.fixture
def area(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Area:
    return build_area(tmp_path, monkeypatch)


def _outside_any_repo(area: Area) -> Path:
    """Leave the repo: git reports none, and the cwd is a private dir outside every root."""
    for module in _github_core_modules("repo"):
        area.monkeypatch.setattr(
            module, "resolve_repo_root", lambda **_kwargs: (None, REPO_ROOT_NOT_A_REPO)
        )
    outside = _mkdir(area.repo.parent / "outside", 0o700)
    area.monkeypatch.chdir(outside)
    return outside


@pytest.mark.parametrize("script", sorted(READERS))
def test_no_repo_refuses_a_file_under_the_working_directory(area: Area, script: str) -> None:
    body = _write(_outside_any_repo(area) / "body.md", 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_no_repo_still_accepts_a_temp_root_file(area: Area, script: str) -> None:
    _outside_any_repo(area)
    body = _owned_600(area)
    assert READERS[script](body, area.repo) == _BODY


def test_no_repo_containment_rule_refuses_the_working_directory(area: Area) -> None:
    body = _write(_outside_any_repo(area) / "body.md", 0o600)
    for module in _github_core_modules("validation"):
        assert module.is_allowed_body_file_path(str(body)) is False
        assert module.is_allowed_body_file_path("body.md") is False
        assert module.is_allowed_body_file_path(str(_owned_600(area))) is True


def test_repo_root_file_is_still_accepted(area: Area) -> None:
    body = _write(_mkdir(area.repo / "drafts", 0o700) / "body.md", 0o600)
    for module in _github_core_modules("validation"):
        assert module.is_allowed_body_file_path(str(body)) is True
    for script in sorted(READERS):
        assert READERS[script](body, area.repo) == _BODY


_PROC_FILE = Path("/proc/self/comm")


@pytest.mark.skipif(not _PROC_FILE.exists(), reason="needs a Linux /proc")
@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize("root", ["cwd", "temp-root", "repo-root"])
def test_refuses_proc_files_under_any_root(area: Area, script: str, root: str) -> None:
    """A harmless /proc file stands in for the ones that expose the environment."""
    if root == "cwd":
        _outside_any_repo(area)
        area.monkeypatch.chdir("/proc")
    elif root == "temp-root":
        area.set_temp_roots(Path("/proc"))
    else:
        for module in _github_core_modules("repo"):
            area.monkeypatch.setattr(
                module, "resolve_repo_root", lambda **_kwargs: (Path("/proc"), REPO_ROOT_OK)
            )
    with pytest.raises(RefusedError):
        READERS[script](_PROC_FILE, area.repo)
    for module in _github_core_modules("validation"):
        assert module.is_allowed_body_file_path(str(_PROC_FILE)) is False


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/proc", True),
        ("/proc/self/comm", True),
        ("/sys/kernel/notes", True),
        ("/dev/null", True),
        ("/dev/fd/0", True),
        ("/dev/shm", True),
        ("/dev/shm/body.md", False),
        ("/dev/shm/private/body.md", False),
        ("/procfs/body.md", False),
        ("/devices/body.md", False),
        ("/tmp/proc/body.md", False),
        ("/home/user/sys/body.md", False),
    ],
)
def test_is_pseudo_filesystem_path(path: str, expected: bool) -> None:
    for module in _github_core_modules("validation"):
        assert module.is_pseudo_filesystem_path(Path(path)) is expected


def test_git_failure_still_accepts_a_temp_root_file(area: Area) -> None:
    for module in _github_core_modules("repo"):
        area.monkeypatch.setattr(
            module, "resolve_repo_root", lambda **_kwargs: (None, REPO_ROOT_GIT_FAILED)
        )
    body = _owned_600(area)
    for script in sorted(READERS):
        assert READERS[script](body, area.repo) == _BODY


@pytest.mark.skipif(not _PROC_FILE.exists(), reason="needs a Linux /proc")
@pytest.mark.parametrize("script", sorted(READERS))
def test_refuses_a_temp_root_symlink_to_proc(area: Area, script: str) -> None:
    link = _mkdir(area.tmp / "private", 0o700) / "body.md"
    link.symlink_to(_PROC_FILE)
    with pytest.raises(RefusedError):
        READERS[script](link, area.repo)


@pytest.mark.parametrize("script", sorted(READERS))
def test_filesystem_root_is_never_an_approved_root(area: Area, script: str) -> None:
    """A repo root of ``/`` would approve every file the caller owns."""
    for module in _github_core_modules("repo"):
        area.monkeypatch.setattr(
            module, "resolve_repo_root", lambda **_kwargs: (Path("/"), REPO_ROOT_OK)
        )
    area.set_temp_roots(Path("/"), area.tmp)
    body = _write(_mkdir(area.repo.parent / "outside", 0o700) / "body.md", 0o600)
    with pytest.raises(RefusedError):
        READERS[script](body, area.repo)
    for module in _github_core_modules("validation"):
        assert module.is_allowed_body_file_path(str(body)) is False
        assert module.is_allowed_body_file_path(str(_owned_600(area))) is True


_DEV_SHM = Path("/dev/shm")


@pytest.mark.skipif(
    not (_DEV_SHM.is_dir() and os.access(_DEV_SHM, os.W_OK)), reason="needs a writable /dev/shm"
)
@pytest.mark.parametrize("script", sorted(READERS))
def test_dev_shm_temp_root_end_to_end(area: Area, script: str, tmp_path: Path) -> None:
    """TMPDIR=/dev/shm is accepted, and a link from it into /proc is not."""
    import shutil
    import tempfile

    area.set_temp_roots(_DEV_SHM)
    private = Path(tempfile.mkdtemp(dir=_DEV_SHM))
    try:
        private.chmod(0o700)
        body = _write(private / "body.md", 0o600)
        assert READERS[script](body, area.repo) == _BODY
        if _PROC_FILE.exists():
            link = private / "link.md"
            link.symlink_to(_PROC_FILE)
            with pytest.raises(RefusedError):
                READERS[script](link, area.repo)
    finally:
        shutil.rmtree(private)
