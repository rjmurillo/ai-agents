"""Tests for the pytest HEAD guard's direct-read fast path (conftest.py).

Trace/reflog/attribution behavior (`_check_head_change`,
`_trace_has_project_head_mutation`, `_reflog_contains_action`, and the
`_guard_real_repo_head` autouse fixture) lives in
`tests/test_pytest_head_guard.py`; this file covers `_direct_read_repo_head`
and its supporting path-safety helpers (`_is_safe_ref_name`, `_common_git_dir`,
`_resolve_ref`, `_fast_path_stat_mode`, `_read_optional_text`,
`_project_git_dir`).
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

from tests.head_guard_test_helpers import _init_git_repo, _load_root_conftest, _run_git

pytestmark = pytest.mark.windows_path


# ---------------------------------------------------------------------------
# Direct-read fast path (`_direct_read_repo_head`): resolves HEAD from Git metadata with no
# subprocess for proven cases, and raises `_HeadFastPathUnresolvedError` for anything it
# cannot prove so the caller falls back to `git rev-parse HEAD`.
# ---------------------------------------------------------------------------


def _refuse_subprocess_run(monkeypatch) -> None:
    """Fail the test if `subprocess.run` is invoked. Patches the stdlib module (not
    `module.subprocess`) so the guard holds whichever module object performs the call."""

    def _fail(*_args, **_kwargs):
        raise AssertionError("git subprocess.run was called; fast path should have handled this")

    monkeypatch.setattr(subprocess, "run", _fail)


def test_direct_read_repo_head_resolves_detached_head(tmp_path, monkeypatch):
    """Positive: HEAD holding a plain object id (detached HEAD) resolves directly."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    head_sha = _init_git_repo(repo)
    (repo / ".git" / "HEAD").write_text(f"{head_sha}\n", encoding="utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    _refuse_subprocess_run(monkeypatch)

    assert module._direct_read_repo_head() == head_sha


def test_direct_read_repo_head_resolves_symbolic_head_with_loose_ref(tmp_path, monkeypatch):
    """Positive: the ordinary case, a symbolic HEAD backed by a loose ref file."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    head_sha = _init_git_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    _refuse_subprocess_run(monkeypatch)

    assert module._direct_read_repo_head() == head_sha


def test_direct_read_repo_head_falls_back_for_packed_refs_only_branch(tmp_path, monkeypatch):
    """Fallback: `git pack-refs --all` removes the loose file. The fast path never scans
    `packed-refs` (see conftest.py's `_resolve_ref` docstring for why), so it raises here
    and `_real_repo_head` falls back to the authoritative subprocess, which still
    resolves."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    head_sha = _init_git_repo(repo)
    branch = _run_git(repo, "branch", "--show-current")
    _run_git(repo, "pack-refs", "--all")
    assert not (repo / ".git" / "refs" / "heads" / branch).exists()  # loose file is gone
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    with pytest.raises(module._HeadFastPathUnresolvedError, match="may be packed"):
        module._direct_read_repo_head()
    assert module._real_repo_head() == head_sha


def test_direct_read_repo_head_resolves_linked_worktree_common_dir(tmp_path, monkeypatch):
    """Positive: a linked worktree's HEAD resolves via its `commondir` to the main git dir."""
    module = _load_root_conftest()
    main_repo = tmp_path / "main"
    _init_git_repo(main_repo)
    linked = tmp_path / "linked"
    _run_git(main_repo, "worktree", "add", "--quiet", str(linked), "-b", "feature")
    feature_sha = _run_git(linked, "rev-parse", "HEAD")
    assert (linked / ".git").is_file()  # linked worktree uses a gitdir pointer file
    monkeypatch.setattr(module, "PROJECT_ROOT", linked)
    _refuse_subprocess_run(monkeypatch)

    assert module._direct_read_repo_head() == feature_sha


def test_direct_read_repo_head_returns_none_for_unborn_head(tmp_path, monkeypatch):
    """Positive: a freshly initialized repo with no commits has a legal unborn HEAD."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "--quiet")
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    _refuse_subprocess_run(monkeypatch)

    assert module._direct_read_repo_head() is None


def test_real_repo_head_matches_git_rev_parse_in_current_checkout():
    """The real checkout may use the fast path or a supported authoritative fallback."""
    module = _load_root_conftest()
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=module.PROJECT_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=True,
    ).stdout.strip()

    assert module._real_repo_head() == expected


def _make_git_dir(repo: Path, head: str | None = None, **files: str) -> Path:
    """Build a bare-bones `.git` dir with the given `HEAD` text and extra metadata files."""
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    if head is not None:
        (git_dir / "HEAD").write_text(head, encoding="utf-8")
    for name, content in files.items():
        (git_dir / name).write_text(content, encoding="utf-8")
    return git_dir


def _repo_with_reftable_storage(repo: Path) -> None:
    """reftable.adoc's dummy `refs/heads/.invalid` HEAD would misread as unborn otherwise."""
    (_make_git_dir(repo, "ref: refs/heads/.invalid\n") / "reftable").mkdir()


def _repo_with_malformed_head(repo: Path) -> None:
    _make_git_dir(repo, "not-a-recognized-head-shape\n")


def _repo_with_packed_only_ref(repo: Path) -> None:
    """No loose ref for HEAD's branch but a `packed-refs` file exists (e.g. after `git
    pack-refs --all`): the fast path cannot rule the ref out of it, so it must raise rather
    than read the ref as absent (see `_resolve_ref`)."""
    git_dir = _make_git_dir(repo, "ref: refs/heads/main\n")
    (git_dir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{'a' * 40} refs/heads/main\n",
        encoding="utf-8",
    )


def _repo_with_unsafe_ref_name(repo: Path) -> None:
    """CWE-22: `..` traversal in the symref target."""
    _make_git_dir(repo, "ref: refs/heads/../../etc/passwd\n")


def _repo_with_windows_style_unsafe_ref_name(repo: Path) -> None:
    """CWE-22: a Windows drive-letter/backslash symref target (see `_is_safe_ref_name`)."""
    _make_git_dir(repo, "ref: refs/heads/..\\..\\C:\\Windows\\System32\\config\\SAM\n")


def _repo_with_non_heads_ref_name(repo: Path) -> None:
    """Only `refs/heads/*` is proven here (see `_is_safe_ref_name`): a HEAD symref into any
    other shared namespace must fall back to Git rather than resolve against `common_dir`."""
    _make_git_dir(repo, "ref: refs/remotes/origin/main\n")


def _repo_with_per_worktree_ref_name(repo: Path) -> None:
    """`man gitrepository-layout`'s `refs` entry lists `refs/bisect` as a per-worktree
    namespace not redirected to `$GIT_COMMON_DIR`; resolving it against the shared
    `common_dir` (as `_resolve_ref` does for `refs/heads/*`) would read the wrong file, so it
    must fall back to Git instead."""
    _make_git_dir(repo, "ref: refs/bisect/bad\n")


_INVALID_UTF8_BYTES = b"\xff\xfe not valid utf-8"


def _repo_with_non_utf8_head(repo: Path) -> None:
    """HEAD holding a byte sequence that is not valid UTF-8 must fall back to Git instead of
    raising an uncaught `UnicodeDecodeError` (see `_read_optional_text`)."""
    (_make_git_dir(repo) / "HEAD").write_bytes(_INVALID_UTF8_BYTES)


def _repo_with_non_utf8_commondir(repo: Path) -> None:
    """A `commondir` file with non-UTF-8 content is unproven, not absent."""
    (_make_git_dir(repo, "ref: refs/heads/main\n") / "commondir").write_bytes(_INVALID_UTF8_BYTES)


def _repo_with_non_utf8_loose_ref(repo: Path) -> None:
    """A loose ref file with non-UTF-8 content is unproven, not absent."""
    git_dir = _make_git_dir(repo, "ref: refs/heads/main\n")
    ref_path = git_dir / "refs" / "heads" / "main"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_bytes(_INVALID_UTF8_BYTES)


def _repo_with_no_git_dir(repo: Path) -> None:
    repo.mkdir()


def _repo_with_head_as_directory(repo: Path) -> None:
    (_make_git_dir(repo) / "HEAD").mkdir()


def _repo_with_broken_commondir(repo: Path) -> None:
    _make_git_dir(repo, "ref: refs/heads/main\n", commondir="../missing-main/.git\n")


@pytest.mark.parametrize(
    ("build_repo", "match"),
    [
        (_repo_with_reftable_storage, "reftable"),
        (_repo_with_malformed_head, "not a recognized shape"),
        (_repo_with_packed_only_ref, "may be packed"),
        (_repo_with_unsafe_ref_name, "safe refs/heads"),
        (_repo_with_windows_style_unsafe_ref_name, "safe refs/heads"),
        (_repo_with_non_heads_ref_name, "safe refs/heads"),
        (_repo_with_per_worktree_ref_name, "safe refs/heads"),
        (_repo_with_non_utf8_head, "could not read HEAD file"),
        (_repo_with_non_utf8_commondir, "could not read commondir file"),
        (_repo_with_non_utf8_loose_ref, "could not read loose ref file"),
        (_repo_with_no_git_dir, "resolve project git directory"),
        (_repo_with_head_as_directory, "could not read HEAD file"),
        (_repo_with_broken_commondir, "commondir target"),
    ],
)
def test_direct_read_repo_head_raises_for_unproven_state(tmp_path, monkeypatch, build_repo, match):
    """Negative: anything the fast path cannot prove raises so the caller falls back to
    `git rev-parse HEAD` instead of guessing."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    build_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    with pytest.raises(module._HeadFastPathUnresolvedError, match=match):
        module._direct_read_repo_head()


@pytest.mark.parametrize(
    ("ref_name", "expected"),
    [
        ("refs/heads/main", True),
        ("refs/heads/feature/x", True),
        ("notrefs/heads/main", False),
        ("/refs/heads/main", False),
        ("refs/heads/../../etc/passwd", False),
        ("refs/heads/..", False),
        # Only `refs/heads/*` is proven here (see `_is_safe_ref_name`'s docstring): every
        # other namespace, whether shared (tags, remotes) or per-worktree (bisect, worktree,
        # rewritten -- `man gitrepository-layout`'s `refs` entry), is rejected.
        ("refs/tags/v1.0", False),
        ("refs/remotes/origin/main", False),
        ("refs/bisect/bad", False),
        ("refs/worktree/example", False),
        ("refs/rewritten/onto", False),
        # PurePosixPath does not treat "\" as a separator, so backslash traversal and UNC
        # forms would pass as one opaque component; ":" anchors a `PureWindowsPath` drive
        # (`C:\Windows`, drive-relative `C:foo`) and is forbidden in a ref name anywhere
        # (git-check-ref-format rule 4). See `_UNSAFE_REF_NAME_CHARACTERS` in conftest.py.
        ("refs/heads/..\\..\\Windows\\System32", False),
        ("refs/heads/C:\\Windows\\System32", False),
        ("refs/heads/C:foo", False),
        ("refs/heads/\\\\server\\share\\x", False),
        ("refs/heads/foo:bar", False),
    ],
)
def test_is_safe_ref_name(ref_name, expected):
    module = _load_root_conftest()

    assert module._is_safe_ref_name(ref_name) is expected


def test_common_git_dir_returns_git_dir_when_no_commondir_file(tmp_path):
    """Edge: a non-worktree repo has no `commondir` file; common dir is git_dir itself."""
    module = _load_root_conftest()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    assert module._common_git_dir(git_dir) == git_dir


def test_resolve_ref_returns_none_when_neither_loose_nor_packed_exists(tmp_path):
    module = _load_root_conftest()

    assert module._resolve_ref(tmp_path, "refs/heads/missing") is None


def test_resolve_ref_raises_for_non_object_id_loose_content(tmp_path):
    """Negative: a legacy chained symref in a loose ref file is not a proven case."""
    module = _load_root_conftest()
    ref_path = tmp_path / "refs" / "heads" / "alias"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text("ref: refs/heads/main\n", encoding="utf-8")

    with pytest.raises(module._HeadFastPathUnresolvedError, match="plain object id"):
        module._resolve_ref(tmp_path, "refs/heads/alias")


def test_resolve_ref_prefers_loose_over_packed(tmp_path):
    """Edge: a loose ref file resolves without ever inspecting a `packed-refs` file that
    happens to exist alongside it (Git's own read-order precedence: loose wins)."""
    module = _load_root_conftest()
    loose_sha = "1" * 40
    packed_sha = "2" * 40
    ref_path = tmp_path / "refs" / "heads" / "main"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text(f"{loose_sha}\n", encoding="utf-8")
    (tmp_path / "packed-refs").write_text(f"{packed_sha} refs/heads/main\n", encoding="utf-8")

    assert module._resolve_ref(tmp_path, "refs/heads/main") == loose_sha


# ---------------------------------------------------------------------------
# OSError-swallowing guards (`_fast_path_stat_mode`, `_read_optional_text`,
# `_project_git_dir`): `Path.is_file()`/`is_dir()`/`exists()` all catch bare `OSError` -- not
# just a missing path -- and return False (`genericpath`, Python 3.14 stdlib). These tests
# prove a non-`FileNotFoundError` failure raises `_HeadFastPathUnresolvedError` (or, for
# `_project_git_dir`, a plain `OSError`) instead of being silently misread as absence.
# ---------------------------------------------------------------------------

# (conftest reader, the `Path` method it must not let swallow an OSError)
_FAST_PATH_READERS = [("_fast_path_stat_mode", "stat"), ("_read_optional_text", "read_text")]


def _raise_permission_error(self, *_args, **_kwargs):
    raise PermissionError("denied")


@pytest.mark.parametrize("reader", [reader for reader, _ in _FAST_PATH_READERS])
def test_fast_path_reader_returns_none_for_missing_path(tmp_path, reader):
    module = _load_root_conftest()

    assert getattr(module, reader)(tmp_path / "missing", "boom") is None


def test_fast_path_readers_return_values_for_existing_paths(tmp_path):
    module = _load_root_conftest()
    target = tmp_path / "present"
    target.write_text("hello", encoding="utf-8")

    assert stat.S_ISREG(module._fast_path_stat_mode(target, "boom"))
    assert module._read_optional_text(target, "boom") == "hello"


@pytest.mark.parametrize(("reader", "path_method"), _FAST_PATH_READERS)
def test_fast_path_reader_raises_for_permission_error(tmp_path, monkeypatch, reader, path_method):
    """A failure that is not `FileNotFoundError` must not be read as absence."""
    module = _load_root_conftest()
    target = tmp_path / "present"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(Path, path_method, _raise_permission_error)

    with pytest.raises(module._HeadFastPathUnresolvedError, match="boom"):
        getattr(module, reader)(target, "boom")


def test_read_optional_text_raises_for_non_utf8_content(tmp_path):
    """Non-UTF-8 bytes (`UnicodeDecodeError`) are unproven, not absent: `_direct_read_repo_head`
    (HEAD), `_common_git_dir` (commondir), and `_resolve_ref` (loose ref) all read through
    `_read_optional_text`, so this one guard covers all three. `_project_git_dir` (`.git`) has
    its own equivalent guard, tested separately."""
    module = _load_root_conftest()
    target = tmp_path / "present"
    target.write_bytes(b"\xff\xfe not valid utf-8")

    with pytest.raises(module._HeadFastPathUnresolvedError, match="boom"):
        module._read_optional_text(target, "boom")


def test_project_git_dir_raises_oserror_for_permission_denied_git_entry(tmp_path, monkeypatch):
    """Negative: a `.git` entry that cannot be stat'd is unproven, not "not a directory"."""
    module = _load_root_conftest()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(Path, "stat", _raise_permission_error)

    with pytest.raises(OSError, match="could not resolve project git directory"):
        module._project_git_dir()


def test_project_git_dir_raises_oserror_for_non_utf8_dot_git_file(tmp_path, monkeypatch):
    """Negative: a `.git` gitdir-pointer file with non-UTF-8 content is unproven, not a
    missing gitdir entry; `_project_git_dir` has its own `read_text` call, not routed through
    `_read_optional_text`, so this is covered separately from
    `test_read_optional_text_raises_for_non_utf8_content`."""
    module = _load_root_conftest()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").write_bytes(b"\xff\xfe not valid utf-8")

    with pytest.raises(OSError, match="could not resolve project git directory"):
        module._project_git_dir()


def test_common_git_dir_raises_for_permission_denied_commondir_target(tmp_path, monkeypatch):
    """Negative: a `commondir` target that cannot be stat'd is unproven, not "does not
    exist"."""
    module = _load_root_conftest()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "commondir").write_text("../main/.git\n", encoding="utf-8")
    monkeypatch.setattr(Path, "stat", _raise_permission_error)

    with pytest.raises(module._HeadFastPathUnresolvedError, match="not accessible"):
        module._common_git_dir(git_dir)


def test_real_repo_head_falls_back_to_subprocess_for_unproven_state(tmp_path, monkeypatch):
    """Fallback: an unprovable on-disk HEAD shape routes through the git subprocess."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("this is not a recognized HEAD shape\n", encoding="utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="fedcba9876543210fedcba9876543210fedcba98\n", stderr=""
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() == "fedcba9876543210fedcba9876543210fedcba98"


def test_real_repo_head_falls_back_to_subprocess_for_non_utf8_head(tmp_path, monkeypatch):
    """Fallback: a HEAD file holding non-UTF-8 bytes (e.g. a foreign-encoded gitdir line on a
    misconfigured checkout) routes through `git rev-parse HEAD` instead of propagating an
    uncaught `UnicodeDecodeError` out of the autouse fixture."""
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_bytes(b"\xff\xfe not valid utf-8")
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="fedcba9876543210fedcba9876543210fedcba98\n", stderr=""
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() == "fedcba9876543210fedcba9876543210fedcba98"
