"""Regression tests for crash-safe mutation worktree isolation."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.testing.mutation_harness import MutationEntry, MutationRunner
from scripts.testing.mutation_workspace import (
    EXIT_BLOCKED,
    EXIT_OK,
    SCRATCH_DIRECTORY,
    check_markers,
    isolated_mutation_worktree,
    marker_directory,
    recover_markers,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("scripts/validation/portability_common.py")


def _child_process() -> subprocess.Popen[str]:
    code = """
import json
import sys
import time
from pathlib import Path
from scripts.testing.mutation_workspace import isolated_mutation_worktree

repo_root = Path(sys.argv[1])
target = Path(sys.argv[2])
with isolated_mutation_worktree(repo_root, [target]) as workspace:
    scratch_target = workspace.root / target
    scratch_target.write_text("# forced mutation\\n", encoding="utf-8")
    print(json.dumps({
        "marker": str(workspace.marker_path),
        "scratch": str(workspace.root),
    }), flush=True)
    time.sleep(300)
"""
    return subprocess.Popen(
        [sys.executable, "-c", code, str(REPO_ROOT), str(TARGET)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _ready_workspace(process: subprocess.Popen[str]) -> dict[str, str]:
    assert process.stdout is not None
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"mutation child exited before ready: {stderr}")
    payload = json.loads(line)
    assert isinstance(payload, dict)
    return payload


def _stop_process(process: subprocess.Popen[str], signum: signal.Signals) -> int:
    os.kill(process.pid, signum)
    return process.wait(timeout=30)


def test_normal_completion_removes_marker_and_scratch() -> None:
    active_before = (REPO_ROOT / TARGET).read_bytes()

    with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
        scratch = workspace.root
        marker = workspace.marker_path
        (scratch / TARGET).write_text("# normal mutation\n", encoding="utf-8")
        assert marker.is_file()

    assert not marker.exists()
    assert not scratch.exists()
    assert (REPO_ROOT / TARGET).read_bytes() == active_before


def test_shared_mutation_runner_never_writes_tracked_source() -> None:
    active_target = REPO_ROOT / TARGET
    original = active_target.read_text(encoding="utf-8")
    old = "not isinstance(value, int) or isinstance(value, bool)"
    entry = MutationEntry(
        name="tracked-source-isolation",
        path=active_target,
        old=old,
        new="not isinstance(value, int)",
        command=(sys.executable, "-c", "raise SystemExit(1)"),
    )

    result = MutationRunner(cwd=REPO_ROOT).run_entry(entry)

    assert result.caught
    assert active_target.read_text(encoding="utf-8") == original


def test_exception_removes_marker_and_scratch() -> None:
    with pytest.raises(RuntimeError, match="forced crash"):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path
            raise RuntimeError("forced crash")

    assert not marker.exists()
    assert not scratch.exists()


def test_timeout_removes_marker_and_scratch() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                check=False,
                timeout=0.01,
            )

    assert not marker.exists()
    assert not scratch.exists()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_catchable_signal_removes_marker_and_scratch(
    signum: signal.Signals,
) -> None:
    process = _child_process()
    workspace = _ready_workspace(process)

    returncode = _stop_process(process, signum)

    assert returncode == 128 + signum
    assert not Path(workspace["marker"]).exists()
    assert not Path(workspace["scratch"]).exists()


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL unavailable")
def test_sigkill_leaves_marker_blocks_push_and_recovers(capsys: pytest.CaptureFixture[str]) -> None:
    active_before = (REPO_ROOT / TARGET).read_bytes()
    process = _child_process()
    workspace = _ready_workspace(process)

    returncode = _stop_process(process, signal.SIGKILL)

    try:
        assert returncode == -signal.SIGKILL
        assert Path(workspace["marker"]).is_file()
        assert Path(workspace["scratch"]).is_dir()
        assert (REPO_ROOT / TARGET).read_bytes() == active_before

        assert check_markers(REPO_ROOT) == EXIT_BLOCKED
        error = capsys.readouterr().err
        assert "push blocked" in error
        assert TARGET.as_posix() in error
        assert "[UNCHANGED]" in error
    finally:
        assert recover_markers(REPO_ROOT) == EXIT_OK

    assert not Path(workspace["marker"]).exists()
    assert not Path(workspace["scratch"]).exists()


def test_concurrent_runs_use_distinct_markers_and_worktrees() -> None:
    first = _child_process()
    second = _child_process()
    first_workspace = _ready_workspace(first)
    second_workspace = _ready_workspace(second)

    assert first_workspace["marker"] != second_workspace["marker"]
    assert first_workspace["scratch"] != second_workspace["scratch"]

    assert _stop_process(first, signal.SIGTERM) == 128 + signal.SIGTERM
    assert _stop_process(second, signal.SIGTERM) == 128 + signal.SIGTERM
    assert not Path(first_workspace["marker"]).exists()
    assert not Path(second_workspace["marker"]).exists()


def test_recovery_refuses_changed_active_target(capsys: pytest.CaptureFixture[str]) -> None:
    marker_root = marker_directory(REPO_ROOT)
    marker_root.mkdir(parents=True, exist_ok=True)
    marker = marker_root / "test-modified-source.json"
    scratch = (REPO_ROOT / SCRATCH_DIRECTORY / "test-modified-source").resolve()
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": 999_999_999,
                "repo_root": str(REPO_ROOT),
                "scratch_worktree": str(scratch),
                "targets": [
                    {
                        "path": TARGET.as_posix(),
                        "sha256": hashlib.sha256(b"different").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        assert recover_markers(REPO_ROOT) == EXIT_BLOCKED
        error = capsys.readouterr().err
        assert TARGET.as_posix() in error
        assert "MODIFIED" in error
        assert marker.exists()
    finally:
        marker.unlink(missing_ok=True)


def test_pre_push_runs_mutation_safety_before_validation() -> None:
    config = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = config["pre-push"]["jobs"]

    assert jobs[1]["name"] == "mutation-safety"
    assert jobs[1]["run"].endswith("scripts.testing.mutation_workspace check")
