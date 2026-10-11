"""Tests for the guard that keeps Copilot out of the local CLI smoke."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard

from scripts.validation import git_hook_policy


@pytest.mark.parametrize(
    "args",
    [
        ["copilot", "--version"],
        ("copilot",),
        "copilot --help",
        b"copilot",
        ["/usr/local/bin/copilot", "-p", "x"],
        [r"C:\tools\Copilot.EXE"],
        [r"C:\npm\copilot.cmd", "skill", "list"],
        [Path("/opt/bin/copilot")],
    ],
)
def test_refuses_every_spelling_of_the_copilot_program(args: object) -> None:
    with pytest.raises(guard.CopilotCallRefusedError, match="requires_copilot"):
        guard.refuse_copilot(args)


@pytest.mark.parametrize(
    "args",
    [
        ["claude", "-p", "copilot"],
        ["codex", "exec"],
        "python -c 'print(1)'",
        ["copilot-language-server"],
        ["/usr/bin/copilotx"],
        [],
        "",
        None,
    ],
)
def test_allows_programs_that_are_not_copilot(args: object) -> None:
    guard.refuse_copilot(args)


def test_guard_is_armed_only_by_the_exact_flag() -> None:
    assert guard.guard_active({guard.LOCAL_SMOKE_ENV: "1"})
    assert not guard.guard_active({guard.LOCAL_SMOKE_ENV: "true"})
    assert not guard.guard_active({})


def test_installed_guard_stops_run_before_the_process_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard.install(monkeypatch.setattr)

    with pytest.raises(guard.CopilotCallRefusedError):
        subprocess.run(["copilot", "--version"], check=False)


def test_installed_guard_checks_the_executable_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: ``executable=`` names the real program, whatever ``args[0]`` says."""
    guard.install(monkeypatch.setattr)

    with pytest.raises(guard.CopilotCallRefusedError):
        subprocess.run(["harmless"], executable="/usr/bin/copilot", check=False)


def test_installed_guard_still_starts_other_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard.install(monkeypatch.setattr)

    result = subprocess.run(
        [sys.executable, "-c", "print('ok')"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "ok"
    with subprocess.Popen([sys.executable, "-c", "pass"]) as proc:
        assert isinstance(proc, subprocess.Popen)
    assert proc.returncode == 0


def _run_unmarked_copilot_test(tmp_path: Path, *, armed: bool) -> subprocess.CompletedProcess[str]:
    """Run a throwaway suite that calls a fake ``copilot`` with no marker."""
    e2e_dir = Path(__file__).resolve().parent
    for name in ("conftest.py", "local_smoke_guard.py"):
        (tmp_path / name).write_text((e2e_dir / name).read_text(encoding="utf-8"), encoding="utf-8")
    fake = tmp_path / "bin" / "copilot"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    fake.chmod(0o755)
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_unmarked.py").write_text(
        "import subprocess\n\n"
        "def test_unmarked_copilot_call():\n"
        f"    subprocess.run([{str(fake)!r}], check=True)\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != guard.LOCAL_SMOKE_ENV}
    if armed:
        env[guard.LOCAL_SMOKE_ENV] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "pytest.ini", "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the fake copilot is a shebang script")
def test_conftest_fails_an_unmarked_copilot_call_under_the_gate_flag(tmp_path: Path) -> None:
    result = _run_unmarked_copilot_test(tmp_path, armed=True)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "must not call Copilot" in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="the fake copilot is a shebang script")
def test_conftest_leaves_copilot_alone_without_the_gate_flag(tmp_path: Path) -> None:
    """Negative control: CI's copilot leg never sets the flag, so calls proceed."""
    result = _run_unmarked_copilot_test(tmp_path, armed=False)

    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_flag_name_matches_the_guard() -> None:
    assert git_hook_policy.CLI_E2E_LOCAL_SMOKE_ENV == guard.LOCAL_SMOKE_ENV
