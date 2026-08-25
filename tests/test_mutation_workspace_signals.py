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
from typing import Protocol

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
# Reaping a killed child is a wait on the kernel, not on the child's own code,
# so it is bounded far tighter than the cap above. It is bounded at all because
# an unbounded second wait can outlive the per-test budget and let
# pytest-timeout preempt the diagnostic the helper exists to print.
SIGNAL_REAP_TIMEOUT_SECONDS = 10
# The worst case for ONE call into _wait_for_exit: burn the whole cap, then
# burn the whole reap bound after SIGKILL. This applies to a SIGKILL caller
# too. Review caught an earlier version of the guard below treating SIGKILL
# waits as free, which contradicted this module's own
# test_wait_for_exit_reports_a_child_that_cannot_be_reaped: a process stuck in
# uninterruptible I/O neither dies on SIGKILL nor reaps, so a SIGKILL-only test
# can spend just as long as any other.
SIGNAL_WAIT_WORST_CASE_SECONDS = SIGNAL_EXIT_TIMEOUT_SECONDS + SIGNAL_REAP_TIMEOUT_SECONDS
# Headroom above the waits a single test can spend, so the diagnostic wins the
# race instead of being preempted. The global --timeout=120 in pyproject.toml
# is too tight for the raised cap, so the tests that wait on a signalled child
# carry their own budget.
SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS = 60
# One wait: the tests that signal a single child.
SIGNAL_TEST_TIMEOUT_SECONDS = (
    SIGNAL_WAIT_WORST_CASE_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
)
# Three waits: test_concurrent_runs_use_distinct_markers_and_worktrees signals
# one child, waits for it, signals the second, and can reach a third wait in
# its finally block. A smaller budget would let pytest-timeout preempt a later
# wait's diagnostic, which is the failure this module exists to make legible.
# Sized by the arithmetic rather than as a flat number so adding a wait forces
# the constant to be revisited.
CONCURRENT_SIGNAL_TEST_TIMEOUT_SECONDS = (
    3 * SIGNAL_WAIT_WORST_CASE_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
)


class _Waitable(Protocol):
    """The subset of ``Popen`` that ``_wait_for_exit`` actually touches.

    Narrowed to these two methods so a test double can stand in without a
    cast. That is not a convenience: the reap-timeout branch is only
    reachable from a child that ignores SIGKILL, which no real process does,
    so the branch is untestable against ``Popen`` itself.
    """

    def wait(self, timeout: float | None = ...) -> int: ...

    def kill(self) -> None: ...


def _wait_for_exit(process: _Waitable, description: str) -> int:
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
        # Recover through the helper rather than calling recover_marker
        # directly, so this covers _recover_if_left_behind's recovering branch
        # on a genuine SIGKILL orphan. A standalone test for that branch would
        # have to create a second real marker, and the repo-global marker
        # directory is shared: tests/test_mutation_workspace.py's
        # test_recovery_refuses_changed_active_target calls recover_markers()
        # over the whole directory, and under --dist loadfile it runs on
        # another worker at the same time. Two concurrent windows on that
        # directory is the #4823 race the _marker_for docstring describes, and
        # a flaky push-blocking test is the exact failure #5108 exists to
        # remove. This test already holds one such window; it does not need a
        # sibling holding another.
        _recover_if_left_behind(Path(workspace["marker"]))

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
    """Count the calls in ``node`` that can each spend a full worst-case wait.

    Every ``_stop_process`` or ``_wait_for_exit`` call counts, including
    SIGKILL ones. An earlier version excluded SIGKILL, reasoning that an
    uncatchable signal cannot let the child outlive the wait. Review showed
    that contradicts this module's own
    ``test_wait_for_exit_reports_a_child_that_cannot_be_reaped``: a process in
    uninterruptible I/O neither dies on SIGKILL nor reaps, so that call can
    burn the cap and then the reap bound like any other. The exclusion would
    have accepted a 60s budget for a SIGKILL-only test.

    Call sites are counted rather than runtime paths. They are sequential
    within a test body, and any of them can be the one that hangs.
    """
    return sum(
        1
        for inner in ast.walk(node)
        if isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id in {"_wait_for_exit", "_stop_process"}
    )


class _UnreapableChild:
    """A child that ignores the cap and then ignores SIGKILL too.

    Both ``wait`` calls raise, which is the only way to reach the reap-timeout
    branch: a real SIGKILLed child reaps immediately, so the negative control
    with a live process cannot exercise it. Deleting that branch would leave
    the suite green without this.
    """

    def __init__(self) -> None:
        self.kill_calls = 0
        # Recorded so the test can assert the reap wait is actually bounded.
        # A fake that raises whatever it is passed cannot otherwise tell a
        # bounded wait from process.wait() with no timeout at all.
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        raise subprocess.TimeoutExpired(cmd="fake-child", timeout=timeout or 0)

    def kill(self) -> None:
        self.kill_calls += 1


@pytest.mark.timeout(SIGNAL_TEST_TIMEOUT_SECONDS)
def test_wait_for_exit_reports_a_child_that_cannot_be_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: a child unreapable after SIGKILL gets its own diagnostic.

    An unbounded second wait could outlive the per-test budget and let
    pytest-timeout preempt the message entirely, so the bound and the message
    are the point. The cap is shortened so this runs in about a second.
    """
    monkeypatch.setitem(_wait_for_exit.__globals__, "SIGNAL_EXIT_TIMEOUT_SECONDS", 1)
    monkeypatch.setitem(_wait_for_exit.__globals__, "SIGNAL_REAP_TIMEOUT_SECONDS", 1)
    child = _UnreapableChild()

    with pytest.raises(pytest.fail.Exception) as failure:
        _wait_for_exit(child, "a child that cannot be reaped")

    assert child.kill_calls == 1, "the helper must SIGKILL before reporting"
    # Both waits must carry a bound. An unbounded reap can outlive the
    # per-test budget, and pytest-timeout would then preempt the message
    # below instead of it printing.
    assert child.wait_timeouts == [1, 1], (
        f"both waits must be bounded, saw {child.wait_timeouts}"
    )

    message = str(failure.value)
    assert "#5108" in message
    assert "a child that cannot be reaped" in message
    assert "did not reap within" in message
    # The distinguishing claim: this is the kernel, not the code under test.
    assert "uninterruptible I/O" in message


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
        required = (
            waits * SIGNAL_WAIT_WORST_CASE_SECONDS + SIGNAL_TEST_TIMEOUT_MARGIN_SECONDS
        )
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
