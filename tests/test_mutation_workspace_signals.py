"""Signal and crash tests for mutation worktree cleanup."""

from __future__ import annotations

import ast
import json
import os
import re
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
# Headroom above the wait cap(s) a single test can spend, so _wait_for_exit's
# diagnostic wins the race instead of being preempted by pytest-timeout. The
# global --timeout=120 in pyproject.toml is too tight for the raised cap, so the
# tests that wait on a signalled child carry their own budget.
# Reaping a SIGKILLed child is a wait on the kernel, not on the child's own
# code, so it is bounded far tighter than the cap above. It is bounded at all
# because an unbounded second wait can outlive the per-test budget and let
# pytest-timeout preempt the diagnostic this helper exists to print.
SIGNAL_REAP_TIMEOUT_SECONDS = 10
SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS = 60
# One sequential wait: the tests that signal a single child.
SIGNAL_TEST_TIMEOUT_SECONDS = SIGNAL_EXIT_TIMEOUT_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
# Two sequential waits: test_concurrent_runs_use_distinct_markers_and_worktrees
# signals one child, waits for it, then signals the second. A one-cap budget
# would let pytest-timeout preempt the second wait's diagnostic, which is the
# failure this module exists to make legible. Sized by the arithmetic rather
# than a flat number so adding a third wait forces the constant to be revisited.
CONCURRENT_SIGNAL_TEST_TIMEOUT_SECONDS = (
    2 * SIGNAL_EXIT_TIMEOUT_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
)


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
        try:
            process.wait(timeout=SIGNAL_REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"#5108: {description} did not exit within "
                f"{SIGNAL_EXIT_TIMEOUT_SECONDS}s (waited {elapsed:.1f}s) and "
                f"then did not reap within {SIGNAL_REAP_TIMEOUT_SECONDS}s of "
                "SIGKILL. A child unreapable after SIGKILL is stuck in the "
                "kernel, typically uninterruptible I/O, not a signal-handling "
                "defect in the code under test.",
                pytrace=False,
            )
        pytest.fail(
            f"#5108: {description} did not exit within "
            f"{SIGNAL_EXIT_TIMEOUT_SECONDS}s (waited {elapsed:.1f}s). The "
            "signal was not delivered, the handler did not run, or the machine "
            "was starved past this cap. The cap is a deadlock backstop, not a "
            "measured bound on signal-delivery latency under load, so it does "
            "not by itself distinguish a code regression from starvation.",
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


def _recover_if_left_behind(marker: Path) -> None:
    """Recover a workspace orphaned by ``_wait_for_exit``'s forced kill.

    ``_wait_for_exit`` SIGKILLs a child that overran the cap. SIGKILL bypasses
    ``isolated_mutation_worktree``'s cleanup, so the marker and its scratch
    worktree survive the failing test, and the next mutation-safety check
    rejects the push for a workspace nothing owns any more. A test that fails
    must not also block the next push, so every call site that knows its marker
    recovers it here. Recovery is the same call the SIGKILL test already makes;
    this only moves it onto the paths that lacked it. Issue #5108.
    """
    if marker.exists():
        assert recover_marker(REPO_ROOT, marker) == EXIT_OK


def _stop_process(process: subprocess.Popen[str], signum: signal.Signals) -> int:
    os.kill(process.pid, signum)
    # The parent sends the signal; "the child sent ..." misread as the child
    # having sent it, which points triage at the wrong process.
    return _wait_for_exit(process, f"the child signalled with {signum.name}")


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

    try:
        returncode = _stop_process(process, signum)

        assert returncode == 128 + signum
        assert not Path(workspace["marker"]).exists()
        assert not Path(workspace["scratch"]).exists()
    finally:
        _recover_if_left_behind(Path(workspace["marker"]))


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_signal_during_cleanup_is_deferred_until_cleanup_completes() -> None:
    process = _cleanup_signal_child_process()
    assert process.stdout is not None
    ready = process.stdout.readline().strip()
    assert ready
    marker, scratch = (Path(value) for value in ready.split("|", maxsplit=1))

    try:
        assert (
            _wait_for_exit(process, "the child signalled during cleanup")
            == 128 + signal.SIGTERM
        )
        assert not marker.exists()
        assert not scratch.exists()
    finally:
        _recover_if_left_behind(marker)


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


@pytest.mark.timeout(CONCURRENT_SIGNAL_TEST_TIMEOUT_SECONDS)
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


def test_recover_if_left_behind_is_a_no_op_when_nothing_was_orphaned(
    tmp_path: Path,
) -> None:
    """Positive path: the passing case must not touch a marker that is gone."""
    _recover_if_left_behind(tmp_path / "never-created.json")


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_recover_if_left_behind_clears_a_real_orphan() -> None:
    """Negative path: an orphan left by a forced kill is recovered, not left.

    Without this, a test that already failed would also block the next push,
    which is the compounding failure the helper exists to prevent.
    """
    process = _child_process()
    workspace = _ready_workspace(process)
    marker = Path(workspace["marker"])

    try:
        # SIGKILL is the signal _wait_for_exit sends on the timeout path, and it
        # bypasses the context manager's cleanup, so this reproduces the orphan
        # rather than simulating it.
        _stop_process(process, signal.SIGKILL)
        assert marker.is_file(), "the orphan this test recovers was not created"

        _recover_if_left_behind(marker)

        assert not marker.exists()
        assert not Path(workspace["scratch"]).exists()
    finally:
        # This test deliberately creates the exact push-blocking state the
        # helper removes. If it fails before recovering, it must not hand that
        # state to the next push, which is the failure it exists to prevent.
        _recover_if_left_behind(marker)


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

        # Parse the value, do not merely look for the label. `"waited " in
        # message` still passes if the number is dropped or replaced with
        # prose, which is precisely the diagnostic contract #5108 adds.
        elapsed_match = re.search(r"waited (\d+(?:\.\d+)?)s", message)
        assert elapsed_match is not None, (
            f"the diagnostic must name the elapsed time as a number: {message!r}"
        )
        elapsed_reported = float(elapsed_match.group(1))
        # The patched cap is 1s, so a plausible reading is at least that and
        # well under the per-test budget. A hardcoded 0.0 would fail the floor.
        assert 1.0 <= elapsed_reported < SIGNAL_TEST_TIMEOUT_SECONDS, (
            f"elapsed {elapsed_reported}s is not a plausible measured wait"
        )
    finally:
        if process.poll() is None:  # pragma: no cover - only on an unexpected path
            process.kill()
            process.wait()

    assert process.poll() is not None, "the helper must not leak the child process"


def _blocking_wait_count(node: ast.FunctionDef) -> int:
    """Count the waits in ``node`` that can each burn a full cap.

    A ``_stop_process(..., signal.SIGKILL)`` call is excluded: SIGKILL cannot
    be caught or ignored, so the child cannot outlive it and that call cannot
    approach the cap. Every other ``_stop_process`` or ``_wait_for_exit`` call
    waits on code that can hang, so each one can spend the whole cap, and they
    run one after another rather than concurrently.
    """
    waits = 0
    for inner in ast.walk(node):
        if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)):
            continue
        if inner.func.id not in {"_wait_for_exit", "_stop_process"}:
            continue
        signal_args = [
            ast.unparse(argument)
            for argument in inner.args
            if isinstance(argument, ast.Attribute)
        ]
        if any(argument.endswith("SIGKILL") for argument in signal_args):
            continue
        waits += 1
    return waits


def _tests_that_wait_on_a_signalled_child() -> list[ast.FunctionDef]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    waiting = {"_wait_for_exit", "_stop_process"}
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id in waiting
            for inner in ast.walk(node)
        )
    ]


def _declared_budget(node: ast.FunctionDef) -> int | None:
    """Resolve this test's pytest-timeout budget to a number, or None."""
    for decorator in node.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "timeout"
            and decorator.args
        ):
            continue
        argument = decorator.args[0]
        if isinstance(argument, ast.Name):
            # Resolve the constant rather than trusting its name: an undersized
            # constant with a plausible name is exactly the regression below.
            return globals().get(argument.id)
        if isinstance(argument, ast.Constant) and isinstance(argument.value, int):
            return argument.value
    return None


def test_every_test_that_waits_on_a_signalled_child_raises_its_budget() -> None:
    """Guard the coupling that makes the #5108 diagnostic reachable at all.

    The wait cap only produces its diagnostic if the test outlives it. With the
    global ``--timeout=120`` sitting below ``SIGNAL_EXIT_TIMEOUT_SECONDS``, a
    test that waits without a large enough budget is killed by pytest-timeout
    first and reports a bare timeout instead.

    This resolves each declared budget to its value and checks it against that
    test's own sequential wait count, rather than only checking a decorator is
    present. Review found that the presence-only form would have accepted the
    concurrent test carrying the one-wait 180s budget against its two 120s
    waits, which is the 240s preemption an earlier round had already fixed.
    """
    undersized = []
    for node in _tests_that_wait_on_a_signalled_child():
        waits = _blocking_wait_count(node)
        required = waits * SIGNAL_EXIT_TIMEOUT_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
        budget = _declared_budget(node)
        if budget is None or budget < required:
            undersized.append(
                f"{node.name}: {waits} sequential wait(s) need >= {required}s, "
                f"declared {budget}"
            )

    assert not undersized, (
        "These tests can spend more time waiting on a signalled child than "
        "their pytest-timeout budget allows, so the #5108 diagnostic is "
        f"preempted before it prints: {undersized}"
    )
