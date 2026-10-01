"""Tests for scripts/validation/lefthook_runner.py (issue #5431)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts.validation import lefthook_runner as runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh shim")


def _completed(returncode: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


def test_uv_ready_when_probe_exits_zero() -> None:
    with (
        mock.patch.object(runner.shutil, "which", return_value="/bin/uv"),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0)) as run,
    ):
        assert runner._uv_is_ready() is True
    assert run.call_args.args[0] == ["uv", "run", "--frozen", "lefthook", "version"]


def test_uv_not_ready_when_probe_fails() -> None:
    with (
        mock.patch.object(runner.shutil, "which", return_value="/bin/uv"),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(2)),
    ):
        assert runner._uv_is_ready() is False


def test_uv_not_ready_when_uv_missing_and_probe_never_runs() -> None:
    with (
        mock.patch.object(runner.shutil, "which", return_value=None),
        mock.patch.object(runner.subprocess, "run") as run,
    ):
        assert runner._uv_is_ready() is False
    run.assert_not_called()


@pytest.mark.parametrize(
    "error", [OSError("boom"), subprocess.TimeoutExpired(cmd="uv", timeout=1)]
)
def test_uv_not_ready_when_probe_cannot_finish(error: Exception) -> None:
    with (
        mock.patch.object(runner.shutil, "which", return_value="/bin/uv"),
        mock.patch.object(runner.subprocess, "run", side_effect=error),
    ):
        assert runner._uv_is_ready() is False


def test_resolve_prefers_uv_over_local_binary() -> None:
    with (
        mock.patch.object(runner, "_uv_is_ready", return_value=True),
        mock.patch.object(runner, "_local_binary", return_value="/x/lefthook") as local,
    ):
        assert runner.resolve_command() == ["uv", "run", "--frozen", "lefthook"]
    local.assert_not_called()


def test_resolve_falls_back_to_local_binary() -> None:
    with (
        mock.patch.object(runner, "_uv_is_ready", return_value=False),
        mock.patch.object(runner, "_local_binary", return_value="/x/lefthook"),
    ):
        assert runner.resolve_command() == ["/x/lefthook"]


def test_resolve_returns_none_when_nothing_works() -> None:
    with (
        mock.patch.object(runner, "_uv_is_ready", return_value=False),
        mock.patch.object(runner, "_local_binary", return_value=None),
    ):
        assert runner.resolve_command() is None


def test_local_binary_prefers_path_then_node_modules(tmp_path: Path) -> None:
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    node_binary = bin_dir / ("lefthook.cmd" if os.name == "nt" else "lefthook")
    node_binary.write_text("", encoding="utf-8")
    node_binary.chmod(0o755)

    with mock.patch.dict(os.environ, {"PATH": str(tmp_path / "empty")}):
        assert Path(runner._local_binary(tmp_path) or "") == node_binary
    with mock.patch.object(runner.shutil, "which", return_value="/on/path/lefthook"):
        assert runner._local_binary(tmp_path) == "/on/path/lefthook"


def test_local_binary_is_none_when_absent(tmp_path: Path) -> None:
    with mock.patch.dict(os.environ, {"PATH": str(tmp_path / "empty")}):
        assert runner._local_binary(tmp_path) is None


def test_main_forwards_arguments_and_returns_child_status() -> None:
    with (
        mock.patch.object(runner, "resolve_command", return_value=["/x/lefthook"]),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(7)) as run,
    ):
        status = runner.main(["run", "pre-commit", "--force"])
    assert status == 7
    assert run.call_args.args[0] == ["/x/lefthook", "run", "pre-commit", "--force"]


def test_main_fails_with_diagnosis_when_unresolvable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(runner, "resolve_command", return_value=None):
        status = runner.main(["run", "pre-commit"])
    err = capsys.readouterr().err
    assert status == runner.EXIT_UNAVAILABLE == 3
    assert "Lefthook itself is unavailable" in err
    assert "Your change is not the cause" in err
    assert "forbidden by ADR-086" in err
    assert runner.REPAIR_COMMAND in err


def test_main_fails_with_diagnosis_when_binary_cannot_start(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        mock.patch.object(runner, "resolve_command", return_value=["/x/lefthook"]),
        mock.patch.object(runner.subprocess, "run", side_effect=OSError("exec format")),
    ):
        status = runner.main([])
    err = capsys.readouterr().err
    assert status == 3
    assert "cannot start /x/lefthook" in err
    assert runner.REPAIR_COMMAND in err


def test_diagnosis_has_no_dashes() -> None:
    assert "–" not in runner.DIAGNOSIS
    assert "—" not in runner.DIAGNOSIS


def test_configured_runner_points_at_this_script() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    assert config["lefthook"] == "python3 scripts/validation/lefthook_runner.py"
    assert (PROJECT_ROOT / "scripts/validation/lefthook_runner.py").is_file()


# --- behavior through a real generated shim -------------------------------

_LEFTHOOK = shutil.which("lefthook")


def _write_exe(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _shim_repo(tmp_path: Path, tools: Path) -> Path:
    """Build a repo whose pre-commit shim was generated by real Lefthook."""
    assert _LEFTHOOK is not None
    repo = tmp_path / "repo"
    (repo / "scripts/validation").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    shutil.copy2(PROJECT_ROOT / "lefthook.yml", repo / "lefthook.yml")
    shutil.copy2(
        PROJECT_ROOT / "scripts/validation/lefthook_runner.py",
        repo / "scripts/validation/lefthook_runner.py",
    )
    subprocess.run(
        [_LEFTHOOK, "install", "--reset-hooks-path"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (tools / "python3").symlink_to(sys.executable)
    return repo


def _run_shim(repo: Path, tools: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{tools}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(repo)}
    return subprocess.run(
        ["sh", ".git/hooks/pre-commit"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_shim_uses_local_binary_when_uv_cannot_resolve(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    marker = tmp_path / "stub-ran.txt"
    _write_exe(tools / "uv", "echo 'Failed to download lefthook' >&2\nexit 2\n")
    _write_exe(tools / "lefthook", f'echo "$@" > "{marker}"\nexit 0\n')
    repo = _shim_repo(tmp_path, tools)
    assert not marker.exists()

    result = _run_shim(repo, tools)

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8").strip() == 'run pre-commit'


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_shim_prefers_uv_when_it_resolves(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    uv_marker = tmp_path / "uv-ran.txt"
    path_marker = tmp_path / "path-ran.txt"
    _write_exe(
        tools / "uv",
        f'[ "$4" = version ] && exit 0\necho "$@" > "{uv_marker}"\nexit 0\n',
    )
    _write_exe(tools / "lefthook", f'touch "{path_marker}"\nexit 0\n')
    repo = _shim_repo(tmp_path, tools)

    result = _run_shim(repo, tools)

    assert result.returncode == 0, result.stderr
    assert uv_marker.read_text(encoding="utf-8").strip() == "run --frozen lefthook run pre-commit"
    assert not path_marker.exists()


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_shim_propagates_hook_job_failure_from_a_working_runner(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    _write_exe(tools / "uv", '[ "$4" = version ] && exit 0\nexit 1\n')
    repo = _shim_repo(tmp_path, tools)

    result = _run_shim(repo, tools)

    assert result.returncode == 1


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_shim_fails_with_diagnosis_when_no_runner_exists(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    _write_exe(tools / "uv", "exit 2\n")
    repo = _shim_repo(tmp_path, tools)

    result = _run_shim(repo, tools)

    assert result.returncode == 3
    assert "Lefthook itself is unavailable" in result.stderr
