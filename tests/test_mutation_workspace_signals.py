"""Signal and crash tests for mutation worktree cleanup."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
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


# Issue #5108: the wait after a signal used to be capped at 30s, a number
# sized on an idle machine. Measured 2026-08-15 during a real pre-push run:
# 7 of 30 runs failed with 7 concurrent `git push` processes on the box, and
# 0 of 30 failed once load fell, on a branch whose diff never touched
# mutation_workspace.py. A failure there rejects the push and costs a retry of
# the full 15-to-25-minute hook suite, so the cap was deciding whether code
# could ship. `.claude/rules/ci-scripts.md` MUST 16: size a pre-push wait for a
# loaded machine, not an idle one.
#
# The cap is a deadlock backstop, not an assertion about signal latency. It has
# to stay below the per-test pytest-timeout budget below, or pytest-timeout
# kills the test first and the diagnostic never prints.
SIGNAL_EXIT_TIMEOUT_SECONDS = 120
# Above SIGNAL_EXIT_TIMEOUT_SECONDS so the diagnostic wins the race. The global
# --timeout=120 in pyproject.toml is too tight for the raised cap, so the tests
# that wait on a signalled child carry their own budget.
SIGNAL_TEST_TIMEOUT_SECONDS = 180


def _wait_for_exit(process: subprocess.Popen[str], description: str) -> int:
    """Wait for a signalled child, naming the elapsed time when it does not exit.

    A bare ``process.wait(timeout=...)`` raises ``TimeoutExpired`` with no
    reading of how long the wait actually took, so a load-induced miss and a
    genuine hang produce the same text. Issue #5108.
    """
    start = time.monotonic()
    try:
        return process.wait(timeout=SIGNAL_EXIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        process.kill()
        process.wait()
        pytest.fail(
            f"#5108: {description} did not exit within "
            f"{SIGNAL_EXIT_TIMEOUT_SECONDS}s (waited {elapsed:.1f}s). At this "
            "cap the signal was not delivered or the handler did not run; "
            "machine load alone does not explain it.",
            pytrace=False,
        )


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
        errors="replace",
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
        errors="replace",
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
    return _wait_for_exit(process, f"the child sent {signum.name}")


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


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
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


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_signal_during_cleanup_is_deferred_until_cleanup_completes() -> None:
    process = _cleanup_signal_child_process()
    assert process.stdout is not None
    ready = process.stdout.readline().strip()
    assert ready
    marker, scratch = (Path(value) for value in ready.split("|", maxsplit=1))

    assert (
        _wait_for_exit(process, "the child signalled during cleanup")
        == 128 + signal.SIGTERM
    )
    assert not marker.exists()
    assert not scratch.exists()


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
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


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_wait_for_exit_returns_the_code_of_a_child_that_exits() -> None:
    """Positive: the raised cap does not change the normal path."""
    process = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(7)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )

    assert _wait_for_exit(process, "a child that exits on its own") == 7


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_wait_for_exit_fails_loudly_when_the_signal_is_never_handled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: a genuine signal-handling regression still fails the test.

    Issue #5108 acceptance criterion 2. The child installs ``SIG_IGN`` for
    SIGTERM, which is exactly what a broken handler looks like from outside:
    the signal lands and the process does not exit. The cap is shortened here
    so the control runs in about a second rather than two minutes; the code
    path under test is the same one the real cap reaches.
    """
    # Patch the binding the helper actually reads. --import-mode=importlib
    # means sys.modules[__name__] is not reliably this module object.
    monkeypatch.setitem(_wait_for_exit.__globals__, "SIGNAL_EXIT_TIMEOUT_SECONDS", 1)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, sys, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(600)\n",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    try:
        # Wait for the handler to be installed. Signalling before the child
        # reaches signal.signal() kills it by the default action instead, and
        # the control silently passes for the wrong reason.
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"

        os.kill(process.pid, signal.SIGTERM)

        with pytest.raises(pytest.fail.Exception) as failure:
            _wait_for_exit(process, "a child ignoring SIGTERM")

        message = str(failure.value)
        assert "#5108" in message
        assert "a child ignoring SIGTERM" in message
        assert "waited " in message, "the diagnostic must name the elapsed time"
    finally:
        if process.poll() is None:  # pragma: no cover - only on an unexpected path
            process.kill()
            process.wait()

    assert process.poll() is not None, "the helper must not leak the child process"
