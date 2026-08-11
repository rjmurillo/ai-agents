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
        assert relative_path.parts[:2] == (".agents", "scratch")
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"


def test_repairs_existing_owner_writable_scratch_mode(tmp_path: Path) -> None:
    scratch = tmp_path / ".agents" / "scratch"
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
    assert (
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())
        == "## Summary\n\nReady.\n"
    )


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
def test_rejects_hard_linked_body_file(
    tmp_path: Path, operation: str
) -> None:
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

    def _swap_then_open(
        path: Path | str, flags: int, *args: object, **kwargs: object
    ) -> int:
        if str(path).startswith("pr-body-"):
            body_path.unlink()
            body_path.write_text("attacker content", encoding="utf-8")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(_MODULE.os, "open", _swap_then_open)
    with pytest.raises(_MODULE.PreparePrBodyError, match="changed before read"):
        _MODULE.read_prepared_pr_body(tmp_path, body.as_posix())


@pytest.mark.parametrize("script", [_SCRIPT, _MIRROR_SCRIPT])
def test_shipped_allocator_executes_from_consumer_cwd(
    tmp_path: Path, script: Path
) -> None:
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
    assert body_path.parent == tmp_path / ".agents" / "scratch"


def test_copilot_mirror_matches_canonical() -> None:
    assert _MIRROR_SCRIPT.read_bytes() == _SCRIPT.read_bytes()


@pytest.mark.parametrize("symlink_name", [".agents", ".agents/scratch"])
def test_rejects_symlinked_parent(tmp_path: Path, symlink_name: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / symlink_name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(_MODULE.PreparePrBodyError):
        _MODULE.prepare_pr_body(tmp_path)

    assert list(outside.iterdir()) == []
