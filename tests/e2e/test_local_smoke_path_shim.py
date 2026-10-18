"""The PATH shim backstop of the local Copilot smoke guard (issue #6506).

The command parser reads a fixed set of launchers. The shim catches a launch by bare name
whichever launcher started it, so these tests start Copilot through forms the parser misses.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard
from local_smoke_command import program_names

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the shim is a shell script")

# Launch forms the parser does not read (the review probe of 2026-10-18). Each starts
# only the launcher name, so the argument-level guard cannot refuse them.
_UNPARSED = [
    ["find", ".", "-maxdepth", "0", "-exec", "copilot", ";"],
    ["bash", "-c", "builtin exec copilot"],
    ["flock", "/dev/null", "copilot"],
    ["taskset", "1", "copilot"],
]


@pytest.fixture
def shim(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Install the shim on a copy of PATH and always remove it."""
    monkeypatch.setenv("PATH", os.environ.get("PATH", os.defpath))
    guard.remove_path_shim()
    try:
        yield guard.install_path_shim()
    finally:
        guard.remove_path_shim()


@posix_only
def test_shim_is_first_on_path_and_exits_non_zero(shim: Path) -> None:
    assert os.environ["PATH"].split(os.pathsep)[0] == str(shim)
    assert shutil.which("copilot") == str(shim / "copilot")

    result = subprocess.run(
        ["copilot", "-p", "x"], capture_output=True, encoding="utf-8", check=False
    )

    assert result.returncode == 126
    assert "must not call Copilot" in result.stderr


@posix_only
@pytest.mark.parametrize("command", _UNPARSED, ids=lambda c: c[0])
def test_shim_stops_a_launcher_the_parser_does_not_read(shim: Path, command: list[str]) -> None:
    if shutil.which(command[0]) is None:
        pytest.skip(f"{command[0]} is not installed")
    assert "copilot" not in program_names(command), "the parser reads this form; pick another"

    result = subprocess.run(command, capture_output=True, encoding="utf-8", check=False)

    # `find -exec ... ;` exits 0 when the command fails, so the shim's message is the proof.
    assert "must not call Copilot" in result.stderr


def test_shim_ships_a_windows_form_that_exits_non_zero(shim: Path) -> None:
    for name in ("copilot.cmd", "copilot.bat"):
        text = (shim / name).read_bytes().decode("utf-8")
        assert "exit /b 126" in text
        assert "\r\n" in text


def test_install_twice_returns_the_same_directory_and_one_path_entry(shim: Path) -> None:
    assert guard.install_path_shim() == shim
    assert os.environ["PATH"].split(os.pathsep).count(str(shim)) == 1


def test_remove_restores_path_and_deletes_the_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/a:/b".replace(":", os.pathsep))
    guard.remove_path_shim()
    shim = guard.install_path_shim()
    assert shim.is_dir()

    guard.remove_path_shim()

    assert os.environ["PATH"] == "/a:/b".replace(":", os.pathsep)
    assert not shim.exists()


def test_remove_without_install_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/a")
    guard.remove_path_shim()

    guard.remove_path_shim()

    assert os.environ["PATH"] == "/a"


def test_install_with_no_path_sets_only_the_shim_and_remove_unsets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard.remove_path_shim()
    monkeypatch.delenv("PATH", raising=False)

    shim = guard.install_path_shim()
    assert os.environ["PATH"] == str(shim)

    guard.remove_path_shim()
    assert "PATH" not in os.environ


def test_remove_keeps_a_path_the_test_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge: a later PATH change is not overwritten with the saved value."""
    monkeypatch.setenv("PATH", "/a")
    guard.remove_path_shim()
    shim = guard.install_path_shim()
    os.environ["PATH"] = "/replaced"

    guard.remove_path_shim()

    assert os.environ["PATH"] == "/replaced"
    assert not shim.exists()


def test_uninstall_also_removes_the_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/a")
    guard.remove_path_shim()
    shim = guard.install_path_shim()

    guard.uninstall()

    assert not shim.exists()
    assert os.environ["PATH"] == "/a"
