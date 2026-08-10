"""Signal and crash tests for mutation worktree cleanup."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.testing import mutation_workspace
from scripts.testing.mutation_workspace import (
    EXIT_BLOCKED,
    EXIT_OK,
    MutationInterrupted,
    check_markers,
    isolated_mutation_worktree,
    marker_directory,
    recover_marker,
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


def _cleanup_signal_child_process() -> subprocess.Popen[str]:
    code = """
import os
import signal
import sys
from pathlib import Path
from scripts.testing import mutation_workspace

repo_root = Path(sys.argv[1])
target = Path(sys.argv[2])
remove_worktree = mutation_workspace._remove_worktree

def signal_during_cleanup(root, scratch):
    os.kill(os.getpid(), signal.SIGTERM)
    remove_worktree(root, scratch)

mutation_workspace._remove_worktree = signal_during_cleanup
with mutation_workspace.isolated_mutation_worktree(repo_root, [target]) as workspace:
    print(f"{workspace.marker_path}|{workspace.root}", flush=True)
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


def _marker_for(scratch_root: Path) -> Path:
    """Return the marker path that belongs to one scratch worktree.

    Verbatim derivation from ``scripts/testing/mutation_workspace.py``'s
    ``isolated_mutation_worktree``::

        run_id = uuid.uuid4().hex
        scratch_root = scratch_parent / run_id
        marker_path = marker_directory(root) / f"{run_id}.json"

    The two tests below never receive a ``MutationWorkspace``, because the
    context manager raises before it yields, so they cannot read
    ``workspace.marker_path`` the way the other nine tests in this module do.
    Naming the file through the scratch directory is that same identity by a
    different route, and each caller asserts the marker exists while the run is
    live, so a wrong derivation fails loudly instead of passing vacuously
    against a path that never existed.

    This replaces ``assert not list(marker_directory(REPO_ROOT).iterdir())``,
    which asserted the shared directory was globally empty. That directory is
    repo-global and ``tests/test_mutation_workspace.py`` writes markers into it
    too, so under ``--dist loadfile`` the sibling module runs on another xdist
    worker at the same moment and the emptiness assertion fails on a file this
    test never created (issue #4823, reproduced 3 of 3 runs at ``-n 2``).
    Emptiness is a property no test can own while another worker runs; the
    lifecycle of its own marker is.
    """
    return marker_directory(REPO_ROOT) / f"{scratch_root.name}.json"


def test_interruption_during_worktree_add_cleans_partial_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Path] = {}

    def interrupt_add(_repo_root: Path, scratch_root: Path) -> None:
        observed["scratch"] = scratch_root
        marker = _marker_for(scratch_root)
        assert marker.is_file(), f"marker absent while the run is live: {marker}"
        observed["marker"] = marker
        scratch_root.mkdir(parents=True)
        raise MutationInterrupted(128 + signal.SIGTERM)

    monkeypatch.setattr(mutation_workspace, "_add_worktree", interrupt_add)

    with pytest.raises(MutationInterrupted):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]):
            pytest.fail("interrupted setup yielded a workspace")

    assert not observed["scratch"].exists()
    assert not observed["marker"].exists()


def test_signal_after_worktree_add_still_runs_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Path] = {}
    add_worktree = mutation_workspace._add_worktree

    def add_then_signal(repo_root: Path, scratch_root: Path) -> None:
        add_worktree(repo_root, scratch_root)
        observed["scratch"] = scratch_root
        marker = _marker_for(scratch_root)
        assert marker.is_file(), f"marker absent while the run is live: {marker}"
        observed["marker"] = marker
        os.kill(os.getpid(), signal.SIGTERM)

    monkeypatch.setattr(mutation_workspace, "_add_worktree", add_then_signal)

    with pytest.raises(MutationInterrupted):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]):
            pytest.fail("signal after add yielded a workspace")

    assert not observed["scratch"].exists()
    assert not observed["marker"].exists()


def test_signal_at_cleanup_transition_still_runs_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InterruptingSignalState:
        pending_signal: int | None = None
        _cleaning_up = False
        _interrupted = False

        @property
        def cleaning_up(self) -> bool:
            return self._cleaning_up

        @cleaning_up.setter
        def cleaning_up(self, value: bool) -> None:
            self._cleaning_up = value
            if value and not self._interrupted:
                self._interrupted = True
                raise MutationInterrupted(128 + signal.SIGTERM)

    state = InterruptingSignalState()
    monkeypatch.setattr(mutation_workspace, "_SignalState", lambda: state)

    with pytest.raises(MutationInterrupted):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path

    assert not scratch.exists()
    assert not marker.exists()


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


def test_signal_during_cleanup_is_deferred_until_cleanup_completes() -> None:
    process = _cleanup_signal_child_process()
    assert process.stdout is not None
    ready = process.stdout.readline().strip()
    assert ready
    marker, scratch = (Path(value) for value in ready.split("|", maxsplit=1))

    assert process.wait(timeout=30) == 128 + signal.SIGTERM
    assert not marker.exists()
    assert not scratch.exists()


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL unavailable")
def test_sigkill_leaves_marker_blocks_push_and_recovers(
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        assert recover_marker(REPO_ROOT, Path(workspace["marker"])) == EXIT_OK

    assert not Path(workspace["marker"]).exists()
    assert not Path(workspace["scratch"]).exists()


def test_concurrent_runs_use_distinct_markers_and_worktrees() -> None:
    first = _child_process()
    second = _child_process()
    workspaces: list[dict[str, str]] = []
    try:
        first_workspace = _ready_workspace(first)
        second_workspace = _ready_workspace(second)
        workspaces.extend((first_workspace, second_workspace))

        assert first_workspace["marker"] != second_workspace["marker"]
        assert first_workspace["scratch"] != second_workspace["scratch"]

        assert _stop_process(first, signal.SIGTERM) == 128 + signal.SIGTERM
        assert _stop_process(second, signal.SIGTERM) == 128 + signal.SIGTERM
        assert not Path(first_workspace["marker"]).exists()
        assert not Path(second_workspace["marker"]).exists()
    finally:
        for process in (first, second):
            if process.poll() is None:
                _stop_process(process, signal.SIGKILL)
        for workspace in workspaces:
            marker = Path(workspace["marker"])
            if marker.exists():
                assert recover_marker(REPO_ROOT, marker) == EXIT_OK
