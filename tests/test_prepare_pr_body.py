"""Tests for the secure PR body path allocator."""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "prepare_pr_body.py"
)
_MIRROR_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "copilot-cli"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "prepare_pr_body.py"
)
_SPEC = importlib.util.spec_from_file_location("prepare_pr_body", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_creates_unique_private_regular_files(tmp_path: Path) -> None:
    first = _MODULE.prepare_pr_body(tmp_path)
    second = _MODULE.prepare_pr_body(tmp_path)

    assert first != second
    for relative_path in (first, second):
        path = tmp_path / relative_path
        assert relative_path.parts[:2] == (".project-toolkit", "scratch")
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"


def test_repairs_existing_owner_writable_scratch_mode(tmp_path: Path) -> None:
    scratch = tmp_path / ".project-toolkit" / "scratch"
    scratch.mkdir(parents=True)
    scratch.chmod(0o775)

    _MODULE.prepare_pr_body(tmp_path)

    assert stat.S_IMODE(scratch.stat().st_mode) == 0o700


def test_windows_without_directory_fds_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_MODULE, "_HAS_DIRECTORY_FDS", False)
    monkeypatch.setattr(_MODULE.os, "name", "nt")

    with pytest.raises(_MODULE.PreparePrBodyError, match="not supported"):
        _MODULE.prepare_pr_body(tmp_path)


def test_rejects_unreplaced_placeholder(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    with pytest.raises(_MODULE.PreparePrBodyError, match="placeholder"):
        _MODULE.reject_unreplaced_placeholder((tmp_path / body).read_text(encoding="utf-8"))


def test_rejects_hard_linked_body_file(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    body_path = tmp_path / body
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    secret.chmod(0o600)
    body_path.unlink()
    body_path.hardlink_to(secret)

    with pytest.raises(_MODULE.PreparePrBodyError, match="plain"):
        _MODULE.write_prepared_pr_body(tmp_path, body.as_posix(), "body")


@pytest.mark.parametrize("script", [_SCRIPT, _MIRROR_SCRIPT])
def test_shipped_allocator_executes_from_consumer_cwd(tmp_path: Path, script: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    body_path = tmp_path / completed.stdout.strip()
    assert body_path.is_file()
    assert body_path.parent == tmp_path / ".project-toolkit" / "scratch"


def test_copilot_mirror_matches_canonical() -> None:
    assert _MIRROR_SCRIPT.read_bytes() == _SCRIPT.read_bytes()


@pytest.mark.parametrize("symlink_name", [".project-toolkit", ".project-toolkit/scratch"])
def test_rejects_symlinked_parent(tmp_path: Path, symlink_name: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / symlink_name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(_MODULE.PreparePrBodyError):
        _MODULE.prepare_pr_body(tmp_path)

    assert list(outside.iterdir()) == []


_BOTH_RULES = (".project-toolkit/scratch/pr-body-*.md", "mode 600", "--prepare-body-file")


def _assert_names_every_rule(message: str) -> None:
    for fragment in _BOTH_RULES:
        assert fragment in message


@pytest.mark.parametrize(
    "bad_path",
    [
        "pr-5534.md",
        ".agents/scratch/pr-body-abc.md",
        ".project-toolkit/scratch/pr-5534.md",
        ".project-toolkit/scratch/nested/pr-body-abc.md",
        "/tmp/pr-body-abc.md",
    ],
)
def test_wrong_body_name_states_name_and_mode_rules(tmp_path: Path, bad_path: str) -> None:
    with pytest.raises(_MODULE.PreparePrBodyError) as caught:
        _MODULE.write_prepared_pr_body(tmp_path, bad_path, "body")

    _assert_names_every_rule(str(caught.value))


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o666])
def test_wrong_body_mode_states_name_and_mode_rules(tmp_path: Path, mode: int) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    (tmp_path / body).write_text("## Summary\n", encoding="utf-8")
    (tmp_path / body).chmod(mode)

    with pytest.raises(_MODULE.PreparePrBodyError) as caught:
        _MODULE.write_prepared_pr_body(tmp_path, body.as_posix(), "body")

    message = str(caught.value)
    _assert_names_every_rule(message)
    assert body.as_posix() in message


_PLACEHOLDER_ONLY = "<!-- replace with PR body -->\n"
_TEMPLATE = ".github/PULL_REQUEST_TEMPLATE.md"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


@pytest.fixture(autouse=True)
def _git_repo_with_base(tmp_path: Path) -> None:
    """Make tmp_path a repo whose origin/main exists and carries no template."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")


def _commit_to_base(root: Path, files: dict[str, bytes], ref: str = "origin/main") -> None:
    """Commit ``files`` on a scratch branch and point the remote-tracking ref at it."""
    _git(root, "checkout", "-q", "-B", "base-work", "main")
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        _git(root, "add", "-f", name)
    _git(root, "commit", "-q", "-m", "template")
    _git(root, "update-ref", f"refs/remotes/{ref}", "HEAD")
    _git(root, "checkout", "-q", "main")
    _git(root, "clean", "-fdxq", "--", ".github", "outside-target.txt")


def _write_template(root: Path, text: str) -> None:
    _commit_to_base(root, {_TEMPLATE: text.encode("utf-8")})


def _body_text(root: Path, body: Path) -> str:
    return (root / body).read_text(encoding="utf-8")


def test_seeds_placeholder_then_repository_template(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\n## Acceptance criteria\n")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == (
        "<!-- replace with PR body -->\n\n## Summary\n\n## Acceptance criteria\n"
    )


def test_seed_is_placeholder_only_without_a_template(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_seed_reads_the_base_ref_not_the_checked_out_branch(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Base template\n")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    template = tmp_path / _TEMPLATE
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text("## Branch edit\nplanted text\n", encoding="utf-8")
    _git(tmp_path, "add", "-f", _TEMPLATE)
    _git(tmp_path, "commit", "-q", "-m", "edit template on the PR branch")

    body = _MODULE.prepare_pr_body(tmp_path)

    seeded = _body_text(tmp_path, body)
    assert "## Base template" in seeded
    assert "planted text" not in seeded


def test_seed_ignores_an_uncommitted_working_tree_template(tmp_path: Path) -> None:
    template = tmp_path / _TEMPLATE
    template.parent.mkdir(parents=True)
    template.write_text("## Untracked\n", encoding="utf-8")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_seed_honors_an_explicit_base_ref(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Main\n")
    _commit_to_base(tmp_path, {_TEMPLATE: b"## Release\n"}, ref="origin/release")

    body = _MODULE.prepare_pr_body(tmp_path, "origin/release")

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY + "\n## Release\n"


def test_unfetched_default_base_fails_closed(tmp_path: Path) -> None:
    _git(tmp_path, "update-ref", "-d", "refs/remotes/origin/main")
    template = tmp_path / _TEMPLATE
    template.parent.mkdir(parents=True)
    template.write_text("## Branch copy\n", encoding="utf-8")

    with pytest.raises(_MODULE.PreparePrBodyError, match="origin/main.*not available locally"):
        _MODULE.prepare_pr_body(tmp_path)

    assert not (tmp_path / ".project-toolkit").exists()


def test_unfetched_explicit_base_names_the_fetch_command(tmp_path: Path) -> None:
    with pytest.raises(_MODULE.PreparePrBodyError, match="git fetch origin release"):
        _MODULE.prepare_pr_body(tmp_path, "origin/release")


def test_default_base_follows_origin_head(tmp_path: Path) -> None:
    _commit_to_base(tmp_path, {_TEMPLATE: b"## Trunk\n"}, ref="origin/trunk")
    _git(tmp_path, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY + "\n## Trunk\n"


@pytest.mark.parametrize("bad_ref", ["", "  ", "--upload-pack=x", "-h"])
def test_rejects_an_option_shaped_or_empty_base_ref(tmp_path: Path, bad_ref: str) -> None:
    with pytest.raises(_MODULE.PreparePrBodyError, match="invalid base ref"):
        _MODULE.prepare_pr_body(tmp_path, bad_ref)


def test_outside_a_git_repository_fails_closed(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    # git walks upward, so the tmp_path repo would answer; point GIT_CEILING_DIRECTORIES.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        with pytest.raises(_MODULE.PreparePrBodyError, match="not available locally"):
            _MODULE.prepare_pr_body(plain)


def test_seed_ignores_a_symlinked_template(tmp_path: Path) -> None:
    link = tmp_path / _TEMPLATE
    link.parent.mkdir(parents=True)
    (tmp_path / "outside-target.txt").write_text("do not copy", encoding="utf-8")
    try:
        link.symlink_to(tmp_path / "outside-target.txt")
    except (OSError, NotImplementedError):
        pytest.skip("platform cannot create symlinks")
    _git(tmp_path, "checkout", "-q", "-B", "base-work", "main")
    _git(tmp_path, "add", "-f", _TEMPLATE)
    if not _git(tmp_path, "ls-files", "-s", _TEMPLATE).startswith("120000"):
        pytest.skip("git did not record the link as a symlink (core.symlinks off)")
    _git(tmp_path, "commit", "-q", "-m", "symlink template")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_seed_ignores_a_template_that_is_not_utf8(tmp_path: Path) -> None:
    _commit_to_base(tmp_path, {_TEMPLATE: b"\xff\xfe\x00bad"})

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_seed_ignores_a_template_path_that_is_a_directory(tmp_path: Path) -> None:
    _commit_to_base(tmp_path, {f"{_TEMPLATE}/inner.md": b"x"})

    assert _MODULE._seed_content(tmp_path.resolve()) == _PLACEHOLDER_ONLY


def test_seed_ignores_an_oversize_template(tmp_path: Path) -> None:
    _write_template(tmp_path, "x" * (64 * 1024 + 1))

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_seed_accepts_a_template_at_the_size_cap(tmp_path: Path) -> None:
    text = "x" * (64 * 1024)
    _write_template(tmp_path, text)

    body = _MODULE.prepare_pr_body(tmp_path)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY + "\n" + text


def test_seed_accepts_an_executable_template(tmp_path: Path) -> None:
    _commit_to_base(tmp_path, {_TEMPLATE: b"## Summary\n"})
    _git(tmp_path, "checkout", "-q", "-B", "base-work", "origin/main")
    _git(tmp_path, "update-index", "--chmod=+x", _TEMPLATE)
    _git(tmp_path, "commit", "-q", "-m", "chmod")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")

    assert _MODULE._seed_content(tmp_path.resolve()) == _PLACEHOLDER_ONLY + "\n## Summary\n"


def test_seed_template_false_skips_git_and_the_base_check(tmp_path: Path) -> None:
    _git(tmp_path, "update-ref", "-d", "refs/remotes/origin/main")
    _write_template_in_worktree = tmp_path / _TEMPLATE
    _write_template_in_worktree.parent.mkdir(parents=True)
    _write_template_in_worktree.write_text("## Branch copy\n", encoding="utf-8")

    body = _MODULE.prepare_pr_body(tmp_path, seed_template=False)

    assert _body_text(tmp_path, body) == _PLACEHOLDER_ONLY


def test_main_reports_an_unfetched_base_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _MODULE.main(["--base", "origin/missing"]) == 2
    assert "origin/missing" in capsys.readouterr().err


def test_main_rejects_unknown_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _MODULE.main(["--bogus"]) == 2
    assert "usage" in capsys.readouterr().err


def test_rejects_seeded_body_that_keeps_the_placeholder_line(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\nfilled in\n")
    body = _MODULE.prepare_pr_body(tmp_path)

    with pytest.raises(_MODULE.PreparePrBodyError, match="placeholder"):
        _MODULE.reject_unreplaced_placeholder((tmp_path / body).read_text(encoding="utf-8"))


def test_reads_seeded_body_once_the_placeholder_line_is_removed(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\nfilled in\n")
    body = _MODULE.prepare_pr_body(tmp_path)
    seeded = (tmp_path / body).read_text(encoding="utf-8")
    (tmp_path / body).write_text(
        seeded.replace("<!-- replace with PR body -->\n\n", ""), encoding="utf-8"
    )

    filled = (tmp_path / body).read_text(encoding="utf-8")
    _MODULE.reject_unreplaced_placeholder(filled)
    assert filled == "## Summary\n\nfilled in\n"


def test_reject_unreplaced_placeholder_flags_the_seed_line() -> None:
    with pytest.raises(_MODULE.PreparePrBodyError, match="placeholder was not replaced"):
        _MODULE.reject_unreplaced_placeholder("<!-- replace with PR body -->\nrest")


def test_reject_unreplaced_placeholder_accepts_a_quoted_marker() -> None:
    _MODULE.reject_unreplaced_placeholder("The seed is `<!-- replace with PR body -->` today.\n")


def test_reject_unreplaced_placeholder_accepts_a_written_body() -> None:
    _MODULE.reject_unreplaced_placeholder("## Summary\n\nDone.\n")


def test_seed_reads_the_template_from_a_repo_subdirectory(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n")
    sub = tmp_path / "pkg" / "inner"
    sub.mkdir(parents=True)

    assert _MODULE._seed_content(sub) == _PLACEHOLDER_ONLY + "\n## Summary\n"


def test_seed_ignores_a_submodule_at_the_template_path(tmp_path: Path) -> None:
    _git(tmp_path, "checkout", "-q", "-B", "base-work", "main")
    _git(
        tmp_path,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{_git(tmp_path, 'rev-parse', 'HEAD')},{_TEMPLATE}",
    )
    _git(tmp_path, "commit", "-q", "-m", "gitlink at the template path")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")

    assert _MODULE._seed_content(tmp_path.resolve()) == _PLACEHOLDER_ONLY


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired(cmd="git", timeout=30),
        FileNotFoundError("git"),
    ],
)
def test_git_that_cannot_run_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(_MODULE.subprocess, "run", boom)

    with pytest.raises(_MODULE.PreparePrBodyError, match="cannot run git"):
        _MODULE.prepare_pr_body(tmp_path)


@pytest.mark.parametrize(
    ("failing_verb", "message"),
    [("ls-tree", "cannot list"), ("cat-file", "cannot read the PR template blob")],
)
def test_failing_git_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_verb: str, message: str
) -> None:
    _write_template(tmp_path, "## Summary\n")
    real_git = _MODULE._git

    def fail_verb(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
        if failing_verb in args:
            return subprocess.CompletedProcess(args, 128, b"", b"fatal: unreadable")
        return real_git(root, *args)

    monkeypatch.setattr(_MODULE, "_git", fail_verb)

    with pytest.raises(_MODULE.PreparePrBodyError, match=message):
        _MODULE.prepare_pr_body(tmp_path)
