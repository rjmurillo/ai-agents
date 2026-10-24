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
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())


def test_reads_replaced_private_body(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    (tmp_path / body).write_text("## Summary\n\nReady.\n", encoding="utf-8")
    assert _MODULE.read_prepared_pr_body(tmp_path, body.as_posix()) == "## Summary\n\nReady.\n"


def test_rejects_symlinked_body_file(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    body_path = tmp_path / body
    target = tmp_path / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    body_path.unlink()
    body_path.symlink_to(target)

    with pytest.raises(_MODULE.PreparePrBodyError, match="plain file"):
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())


@pytest.mark.parametrize("operation", ["read", "write"])
def test_rejects_hard_linked_body_file(tmp_path: Path, operation: str) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    body_path = tmp_path / body
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    secret.chmod(0o600)
    body_path.unlink()
    body_path.hardlink_to(secret)

    with pytest.raises(_MODULE.PreparePrBodyError, match="plain"):
        if operation == "read":
            _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())
        else:
            _MODULE.write_prepared_pr_body(tmp_path, body.as_posix(), "body")


def test_rejects_file_swapped_between_check_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    body_path = tmp_path / body
    real_open = _MODULE.os.open

    def _swap_then_open(path: Path | str, flags: int, *args: object, **kwargs: object) -> int:
        if str(path).startswith("pr-body-"):
            body_path.unlink()
            body_path.write_text("attacker content", encoding="utf-8")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(_MODULE.os, "open", _swap_then_open)
    with pytest.raises(_MODULE.PreparePrBodyError, match="changed before read"):
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())


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


@pytest.mark.parametrize("operation", ["read", "write"])
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
def test_wrong_body_name_states_name_and_mode_rules(
    tmp_path: Path, operation: str, bad_path: str
) -> None:
    with pytest.raises(_MODULE.PreparePrBodyError) as caught:
        if operation == "read":
            _MODULE.read_prepared_pr_body(tmp_path, bad_path)
        else:
            _MODULE.write_prepared_pr_body(tmp_path, bad_path, "body")

    _assert_names_every_rule(str(caught.value))


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o666])
def test_wrong_body_mode_states_name_and_mode_rules(
    tmp_path: Path, operation: str, mode: int
) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    (tmp_path / body).write_text("## Summary\n", encoding="utf-8")
    (tmp_path / body).chmod(mode)

    with pytest.raises(_MODULE.PreparePrBodyError) as caught:
        if operation == "read":
            _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())
        else:
            _MODULE.write_prepared_pr_body(tmp_path, body.as_posix(), "body")

    message = str(caught.value)
    _assert_names_every_rule(message)
    assert body.as_posix() in message


@pytest.mark.parametrize("mode", [0o600, 0o400, 0o700])
def test_owner_only_body_is_not_rejected_for_mode(tmp_path: Path, mode: int) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)
    (tmp_path / body).write_text("## Summary\n", encoding="utf-8")
    (tmp_path / body).chmod(mode)

    assert _MODULE.read_prepared_pr_body(tmp_path, body.as_posix()) == "## Summary\n"


def _write_template(root: Path, text: str) -> None:
    template = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(text, encoding="utf-8")


def test_seeds_placeholder_then_repository_template(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\n## Acceptance criteria\n")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == (
        "<!-- replace with PR body -->\n\n## Summary\n\n## Acceptance criteria\n"
    )


def test_seed_is_placeholder_only_without_a_template(tmp_path: Path) -> None:
    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"


def test_seed_ignores_a_symlinked_template(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do not copy", encoding="utf-8")
    template = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    template.parent.mkdir()
    template.symlink_to(secret)

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"


def test_seed_ignores_a_template_that_is_not_utf8(tmp_path: Path) -> None:
    template = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    template.parent.mkdir()
    template.write_bytes(b"\xff\xfe\x00bad")

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"


_PLACEHOLDER_ONLY = "<!-- replace with PR body -->\n"


def test_seed_ignores_a_symlinked_github_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "PULL_REQUEST_TEMPLATE.md").write_text("outside secret", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".github").symlink_to(outside, target_is_directory=True)

    body = _MODULE.prepare_pr_body(repo)

    assert (repo / body).read_text(encoding="utf-8") == _PLACEHOLDER_ONLY


def test_seed_ignores_a_hardlinked_template(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n")
    template = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    (tmp_path / "second-link.md").hardlink_to(template)

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == _PLACEHOLDER_ONLY


def test_seed_ignores_an_oversize_template(tmp_path: Path) -> None:
    _write_template(tmp_path, "x" * (64 * 1024 + 1))

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == _PLACEHOLDER_ONLY


def test_seed_accepts_a_template_at_the_size_cap(tmp_path: Path) -> None:
    text = "x" * (64 * 1024)
    _write_template(tmp_path, text)

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == _PLACEHOLDER_ONLY + "\n" + text


def test_seed_ignores_a_template_that_is_a_directory(tmp_path: Path) -> None:
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").mkdir(parents=True)

    body = _MODULE.prepare_pr_body(tmp_path)

    assert (tmp_path / body).read_text(encoding="utf-8") == _PLACEHOLDER_ONLY


def test_seed_ignores_a_template_owned_by_another_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(tmp_path, "## Summary\n")
    real_uid = _MODULE.os.getuid()
    monkeypatch.setattr(_MODULE.os, "getuid", lambda: real_uid + 1)

    seed = _MODULE._seed_content(tmp_path.resolve())

    assert seed == _PLACEHOLDER_ONLY


@pytest.mark.parametrize("mode", [0o666, 0o646, 0o602, 0o777])
def test_seed_ignores_a_world_writable_template(tmp_path: Path, mode: int) -> None:
    _write_template(tmp_path, "## Summary\n")
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").chmod(mode)

    assert _MODULE._seed_content(tmp_path.resolve()) == _PLACEHOLDER_ONLY


@pytest.mark.parametrize("mode", [0o600, 0o644, 0o664, 0o640, 0o444])
def test_seed_accepts_a_template_that_is_not_world_writable(tmp_path: Path, mode: int) -> None:
    """A umask of 002 makes a fresh checkout mode 664, so group-write must pass."""
    _write_template(tmp_path, "## Summary\n")
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").chmod(mode)

    seed = _MODULE._seed_content(tmp_path.resolve())

    assert seed == _PLACEHOLDER_ONLY.rstrip("\n") + "\n\n## Summary\n"


def test_seed_is_placeholder_only_without_directory_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(tmp_path, "## Summary\n")
    monkeypatch.setattr(_MODULE, "_HAS_DIRECTORY_FDS", False)

    assert _MODULE._seed_content(tmp_path.resolve()) == _PLACEHOLDER_ONLY


def test_rejects_seeded_body_that_keeps_the_placeholder_line(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\nfilled in\n")
    body = _MODULE.prepare_pr_body(tmp_path)

    with pytest.raises(_MODULE.PreparePrBodyError, match="placeholder"):
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())


def test_reads_seeded_body_once_the_placeholder_line_is_removed(tmp_path: Path) -> None:
    _write_template(tmp_path, "## Summary\n\nfilled in\n")
    body = _MODULE.prepare_pr_body(tmp_path)
    seeded = (tmp_path / body).read_text(encoding="utf-8")
    (tmp_path / body).write_text(
        seeded.replace("<!-- replace with PR body -->\n\n", ""), encoding="utf-8"
    )

    assert _MODULE.read_prepared_pr_body(tmp_path, body.as_posix()) == "## Summary\n\nfilled in\n"


def test_reject_unreplaced_placeholder_flags_the_seed_line() -> None:
    with pytest.raises(_MODULE.PreparePrBodyError, match="placeholder was not replaced"):
        _MODULE.reject_unreplaced_placeholder("<!-- replace with PR body -->\nrest")


def test_reject_unreplaced_placeholder_accepts_a_quoted_marker() -> None:
    _MODULE.reject_unreplaced_placeholder("The seed is `<!-- replace with PR body -->` today.\n")


def test_reject_unreplaced_placeholder_accepts_a_written_body() -> None:
    _MODULE.reject_unreplaced_placeholder("## Summary\n\nDone.\n")
