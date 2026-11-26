"""Run the ship Windows seams on a real Windows host.

The other ship tests patch ``os.name`` to reach these paths. These do not: they
need cmd.exe, PATHEXT, and a cp1252 console, so they run only on the Windows
runner that ``scripts/ci/run_pytest_windows.py`` drives by the marker below.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.windows_path,
    pytest.mark.skipif(os.name != "nt", reason="needs Windows"),
]


@pytest.fixture
def windows_module(scripts):
    """The real ``_ship_windows`` module the scripts loaded."""
    return sys.modules["_ship_windows"]


@pytest.fixture
def fake_az(tmp_path, monkeypatch):
    """Put an ``az.cmd`` that echoes its arguments first on PATH; return its path."""
    script = tmp_path / "az.cmd"
    script.write_text("@echo off\r\necho %*\r\n", encoding="ascii")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    return script


def test_find_program_finds_az_cmd_on_path(windows_module, fake_az):
    found = windows_module.find_program("az")
    assert found is not None
    assert os.path.samefile(found, fake_az)


def test_a_batch_command_runs_with_each_argument_literal(windows_module, fake_az):
    built = windows_module.command(["az", "a&b", "c d"])
    assert built is not None
    done = subprocess.run(
        built, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    assert done.returncode == 0, done.stderr
    assert "a&b" in done.stdout
    assert "c d" in done.stdout


def test_an_argument_with_a_percent_sign_is_refused(windows_module, fake_az):
    assert windows_module.command(["az", "50%"]) is None


def test_an_unfound_program_is_left_for_the_caller(windows_module, fake_az):
    assert windows_module.command(["no-such-ship-program", "x"]) == ["no-such-ship-program", "x"]


def test_planted_programs_sees_a_file_that_createprocess_would_run(
    windows_module, tmp_path, monkeypatch
):
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    (tmp_path / "git.exe").write_bytes(b"")
    assert [name.lower() for name in windows_module.planted_programs(tmp_path)] == ["git.exe"]


def test_emit_replaces_a_character_the_console_code_page_cannot_hold(scripts, monkeypatch):
    common = scripts[0]
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="")
    monkeypatch.setattr(sys, "stdout", console)
    result = common.Result("ship_detect.py", frozenset())
    result.add("BRANCH", "feat/中文")
    result.next("preflight")
    code = common.emit(result, "human", None)
    console.flush()
    assert code == 0
    printed = raw.getvalue().decode("cp1252")
    assert "BRANCH: feat/" in printed
    assert "NEXT: preflight" in printed


def test_a_strict_cp1252_console_raises_without_the_replacement():
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with pytest.raises(UnicodeEncodeError):
        console.write("中")
