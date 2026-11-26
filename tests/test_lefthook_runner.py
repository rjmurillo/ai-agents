"""Tests for scripts/validation/lefthook_runner.py (issue #5431)."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts.validation import lefthook_runner as runner
from tests.support.lefthook_binary import resolve_lefthook

# The runner imports its sibling by bare name; patch the module object it holds.
report_module = importlib.import_module(runner.run_hook_with_report.__module__)

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


@pytest.mark.parametrize("error", [OSError("boom"), subprocess.TimeoutExpired(cmd="uv", timeout=1)])
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
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
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
    assert "\u2013" not in runner.DIAGNOSIS
    assert "\u2014" not in runner.DIAGNOSIS


def test_configured_runner_points_at_this_script() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    assert config["lefthook"] == "python3 scripts/validation/lefthook_runner.py"
    assert (PROJECT_ROOT / "scripts/validation/lefthook_runner.py").is_file()
    # A printed pre-push rerun must use the same command the shim runs (issue #6884).
    assert " ".join(runner.RUNNER_COMMAND) == config["lefthook"]


# --- delete-only pushes run only the ref guard jobs ------------------------

ZERO_SHA = "0" * 40
SOME_SHA = "954729fa9af4ef395fd0b8643f9c50a0b04b7d36"
DELETE_LINE = f"(delete) {ZERO_SHA} refs/heads/old {SOME_SHA}\n"
UPDATE_LINE = f"refs/heads/topic {SOME_SHA} refs/heads/topic {ZERO_SHA}\n"
GIT_ARGUMENTS = ["origin", "https://example.test/repo.git"]
# Pre-push jobs that read stdin but inspect tree content, so a delete skips them.
TREE_JOBS_WITH_STDIN = frozenset({"security-scan", "hook-anchoring-e2e", "plugin-load-e2e"})


def _guard_job_args() -> list[str]:
    return [item for job in runner.REF_GUARD_JOBS for item in ("--job", job)]


def _pre_push(stdin: bytes | None, *flags: str) -> list[str]:
    arguments = ["run", "pre-push", *flags, *GIT_ARGUMENTS]
    with mock.patch.object(runner, "lefthook_file_args", return_value=["--file=a.py"]):
        return runner._child_arguments(arguments, stdin)


def _job_names(jobs: list[dict]) -> list[str]:
    names: list[str] = []
    for job in jobs:
        if "name" in job:
            names.append(job["name"])
        names.extend(_job_names(job.get("group", {}).get("jobs", [])))
    return names


def _stdin_job_names(jobs: list[dict]) -> list[str]:
    names: list[str] = []
    for job in jobs:
        if job.get("use_stdin"):
            names.append(job["name"])
        names.extend(_stdin_job_names(job.get("group", {}).get("jobs", [])))
    return names


def _pre_push_jobs() -> list[dict]:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    return config["pre-push"]["jobs"]


def test_delete_only_push_adds_one_job_flag_per_ref_guard() -> None:
    result = _pre_push(DELETE_LINE.encode())

    assert result == [
        "run",
        "pre-push",
        "--file=a.py",
        *_guard_job_args(),
        "--",
        *GIT_ARGUMENTS,
    ]


def test_delete_only_push_with_several_deletes_adds_the_jobs() -> None:
    stdin = (DELETE_LINE + DELETE_LINE.replace("old", "older")).encode()

    assert _guard_job_args() == _pre_push(stdin)[3 : 3 + 2 * len(runner.REF_GUARD_JOBS)]


def test_delete_only_push_says_tree_jobs_were_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    _pre_push(DELETE_LINE.encode())

    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "skipped the tree jobs" in err
    assert "only deletes refs" in err
    assert f"{len(runner.REF_GUARD_JOBS)} ref guard jobs run" in err


def test_mixed_delete_and_update_keeps_every_job() -> None:
    stdin = (DELETE_LINE + UPDATE_LINE).encode()

    assert "--job" not in _pre_push(stdin)


def test_update_before_delete_keeps_every_job() -> None:
    stdin = (UPDATE_LINE + DELETE_LINE).encode()

    assert "--job" not in _pre_push(stdin)


def test_update_only_push_keeps_every_job(capsys: pytest.CaptureFixture[str]) -> None:
    assert "--job" not in _pre_push(UPDATE_LINE.encode())
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("stdin", [None, b"", b"\n"])
def test_empty_stdin_keeps_every_job(stdin: bytes | None) -> None:
    assert "--job" not in _pre_push(stdin)


@pytest.mark.parametrize(
    "flags",
    [
        ("--job", "python-tests"),
        ("--job=python-tests",),
        ("--tag", "fast"),
        ("--command", "lint"),
    ],
)
def test_caller_supplied_scope_flag_is_respected(
    flags: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    result = _pre_push(DELETE_LINE.encode(), *flags)

    assert result == ["run", "pre-push", "--file=a.py", *flags, "--", *GIT_ARGUMENTS]
    assert capsys.readouterr().err == ""


def test_caller_supplied_file_flag_is_respected() -> None:
    arguments = ["run", "pre-push", "--file", "x.py", *GIT_ARGUMENTS]

    result = runner._child_arguments(arguments, DELETE_LINE.encode())

    assert result == ["run", "pre-push", "--file", "x.py", "--", *GIT_ARGUMENTS]


def test_other_hooks_never_get_job_flags() -> None:
    arguments = ["run", "pre-commit"]

    assert runner._child_arguments(arguments, DELETE_LINE.encode()) == arguments


def test_malformed_ref_line_still_stops_the_push() -> None:
    arguments = ["run", "pre-push", *GIT_ARGUMENTS]

    with pytest.raises(runner.PushFileListError):
        runner._child_arguments(arguments, b"not a ref line\n")


def test_ref_guard_list_names_only_real_pre_push_jobs() -> None:
    real = set(_job_names(_pre_push_jobs()))

    assert set(runner.REF_GUARD_JOBS) <= real
    assert len(set(runner.REF_GUARD_JOBS)) == len(runner.REF_GUARD_JOBS)


def test_every_stdin_job_is_a_ref_guard_or_a_known_tree_job() -> None:
    stdin_jobs = set(_stdin_job_names(_pre_push_jobs()))

    unclassified = stdin_jobs - set(runner.REF_GUARD_JOBS) - TREE_JOBS_WITH_STDIN
    assert not unclassified, f"classify as ref guard or tree job: {sorted(unclassified)}"
    assert TREE_JOBS_WITH_STDIN <= set(_job_names(_pre_push_jobs()))
    assert not TREE_JOBS_WITH_STDIN & set(runner.REF_GUARD_JOBS)


def test_protected_branch_guard_runs_on_a_delete() -> None:
    # check_push_refs refusing a protected delete is covered end to end by
    # tests/test_pre_push_ref_guard_entrypoint.py. This pins that a delete reaches it.
    assert "push-ref-policy" in runner.REF_GUARD_JOBS
    assert "push-ref-policy" in _pre_push(DELETE_LINE.encode())


# --- behavior through a real generated shim -------------------------------

_LEFTHOOK = resolve_lefthook()


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
    for module in ("lefthook_runner.py", "lefthook_failure_report.py", "push_file_list.py"):
        shutil.copy2(
            PROJECT_ROOT / "scripts/validation" / module, repo / "scripts/validation" / module
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
    assert marker.read_text(encoding="utf-8").strip() == "run pre-commit"


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
