"""One deadline for the whole security scan, not one per pushed ref.

`scan_pushed_heads` was the last unbounded path in pre-push. It loops over
pushed refs, each ref's scan batches its targets, and every batch got a fresh
`_run_command` allowance, so a container push cost refs times batches times the
150s subprocess clamp. ADR-104 rule 8 says a local tier must not be able to
outlive the environment it runs in, and a clamp on one child says nothing about
a job that runs many. The identical defect in `run_pytest` was found by review
on PR #5319; this module covers the sibling fix.

Nothing here runs semgrep. The scan itself is covered in
`tests/test_lefthook_integration.py`; what is under test is the arithmetic that
decides whether a scan is allowed to start.

Coverage:

- positive: the job's budget is the container ceiling when one applies, and the
  workstation figure when none does.
- negative: a ref whose turn comes after the deadline is refused, semgrep is
  never reached for it, and the message names the budget.
- edge: `_run_semgrep_tree` refuses an expired deadline without spawning, and
  the wiring test proves `scan_pushed_heads` passes its deadline down at all.
"""

from __future__ import annotations

import io
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy

_CONTAINER_CEILING = policy.CONTAINER_SUBPROCESS_CEILING_SECONDS


def _detector(*, in_container: bool) -> types.ModuleType:
    """A stand-in for the sibling module `_arm_container_watchdog` imports.

    Written through `__dict__` because the two obvious spellings each fail a
    different gate. `module._is_remote_container = ...` fails mypy, which knows
    ModuleType has no such attribute, and `setattr(module, "...", ...)` is
    rewritten back into that spelling by ruff's B010 autofix, so the pair
    oscillates. Assigning into the namespace says the same thing and is what
    both are describing anyway.
    """
    module = types.ModuleType("run_workflow_local_test")
    module.__dict__["_is_remote_container"] = lambda: in_container
    return module


def _update(head: str) -> policy.PushUpdate:
    source = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "2" * 40)
    return policy.PushUpdate(source, "base", head, f"base..{head}", "a")


def _arrange(
    monkeypatch: pytest.MonkeyPatch, heads: list[str], *, clamp: Any
) -> None:
    """Point `scan_pushed_heads` at `heads` with one scannable path each."""
    monkeypatch.setattr(policy, "_push_updates", lambda *_a: [_update(h) for h in heads])
    monkeypatch.setattr(policy, "_changed_commit_paths", lambda *_a: ["source.py"])
    monkeypatch.setattr(policy, "_commit_paths", lambda *_a: ["source.py"])
    monkeypatch.setattr(policy, "_container_clamped", clamp)


def _record_deadlines(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture each head's deadline, failing loudly when none is passed.

    The keyword has no default here on purpose. A fake that defaults it absorbs
    the regression these tests exist to catch: with `deadline=0.0` standing in,
    a `scan_pushed_heads` that stopped passing one records three identical
    sentinels, "one job, one deadline" holds, and "not more than the ceiling"
    holds by a mile because the sentinel is in 1970. Both assertions pass while
    the job is unbounded. Found by mutation on PR #5319, in a test written on
    that same branch to close the same class of hole.
    """
    seen: list[float] = []

    def record(_head: str, *_a: object, deadline: float, **_k: object) -> int:
        seen.append(deadline)
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", record)
    return seen


def test_the_job_carries_a_deadline_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wiring: a bound the caller never passes down bounds nothing.

    `_scan_pushed_head` accepts `deadline=None` so direct unit callers keep
    working, which means the production path can regress to the unbounded shape
    without any of the behavior tests below failing: they would simply stop
    being about a deadline. This asserts the argument arrives.
    """
    seen: list[float | None] = []
    _arrange(monkeypatch, ["head1"], clamp=lambda seconds: seconds)

    # This fake keeps the default that `_record_deadlines` deliberately drops:
    # it is the test that asserts the argument arrived at all, so it has to be
    # able to observe its absence rather than raise on it.
    def record(_head: str, *_a: object, deadline: float | None = None, **_k: object) -> int:
        seen.append(deadline)
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", record)

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0
    assert seen and seen[0] is not None, (
        "scan_pushed_heads called _scan_pushed_head without a deadline, so "
        "every head gets its own budget again and the job is unbounded across "
        "refs. See ADR-104 rule 8."
    )


def test_a_container_bounds_the_whole_scan_not_each_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deadline is drawn from the clamped budget, so N refs cannot multiply."""
    _arrange(
        monkeypatch,
        ["head1", "head2", "head3"],
        clamp=lambda seconds: min(seconds, _CONTAINER_CEILING),
    )
    seen = _record_deadlines(monkeypatch)

    started = time.monotonic()
    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0

    assert len(seen) == 3, "all three heads should have been offered a scan"
    assert seen[0] > started, (
        f"the deadline is {seen[0]:.0f} against a start of {started:.0f}, so it "
        "is not a real future time. A deadline in the past bounds nothing and "
        "makes the ceiling assertion below hold for the wrong reason."
    )
    assert len(set(seen)) == 1, (
        f"the heads got {len(set(seen))} different deadlines. One job, one "
        "deadline: a per-head deadline is the unbounded shape wearing the "
        "new argument."
    )
    assert seen[0] - started <= _CONTAINER_CEILING + 1, (
        f"the deadline is {seen[0] - started:.0f}s out against a "
        f"{_CONTAINER_CEILING:.0f}s container ceiling, so the budget was not "
        "clamped and three refs can still outlive the container."
    )


def test_a_workstation_keeps_the_semgrep_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control for the test above: without a clamp the budget is the old one.

    A one-ref push on a workstation is unchanged by this work, which is the
    claim that keeps ADR-054's enforced 900s security-scan budget intact. If
    this and the container test ever agree, the clamp is doing nothing and the
    assertion above is reading `SEMGREP_TIMEOUT_SECONDS` under another name.
    """
    _arrange(monkeypatch, ["head1"], clamp=lambda seconds: seconds)
    seen = _record_deadlines(monkeypatch)

    started = time.monotonic()
    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0
    budget = seen[0] - started

    assert budget > _CONTAINER_CEILING, (
        f"the workstation budget is {budget:.0f}s, at or under the container "
        f"ceiling of {_CONTAINER_CEILING:.0f}s. The two cases are supposed to "
        "differ; if they do not, neither test is about the clamp."
    )
    assert budget <= policy.SEMGREP_TIMEOUT_SECONDS + 1


def test_a_later_ref_is_refused_once_the_budget_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal, and the proof that semgrep is not reached for that ref."""
    scanned: list[str] = []
    _arrange(monkeypatch, ["head1", "head2"], clamp=lambda seconds: seconds)

    clock = {"now": 1_000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    def burn_the_budget(head: str, *_a: object, **_k: object) -> int:
        scanned.append(head)
        clock["now"] += policy.SEMGREP_TIMEOUT_SECONDS + 1
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", burn_the_budget)

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 1
    assert scanned == ["head1"], (
        f"expected the second head to be refused, but semgrep saw {scanned}. "
        "The deadline is not checked between refs."
    )
    err = capsys.readouterr().err
    assert "head2" in err and "budget" in err, (
        f"the refusal does not say which ref was dropped or why: {err!r}"
    )


def test_the_refusal_needs_the_budget_to_be_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Inverted control: the same two refs pass when the budget survives.

    Without this, the test above passes for a `scan_pushed_heads` that refuses
    the second ref unconditionally, which would be a worse gate than the
    unbounded one it replaced.
    """
    scanned: list[str] = []
    _arrange(monkeypatch, ["head1", "head2"], clamp=lambda seconds: seconds)

    clock = {"now": 1_000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    def cheap_scan(head: str, *_a: object, **_k: object) -> int:
        scanned.append(head)
        clock["now"] += 1.0
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", cheap_scan)

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0
    assert scanned == ["head1", "head2"]


def test_an_expired_deadline_stops_semgrep_before_it_spawns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The batch loop's half of the bound.

    Refs multiply the scan and so do target batches within one ref, so checking
    only between refs would leave a single ref with many batches unbounded.
    """
    monkeypatch.setattr(policy, "_semgrep_target_batches", lambda targets, _root: [targets])
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_a, **_k: pytest.fail("semgrep ran after the budget was gone"),
    )

    result = policy._run_semgrep_tree(
        tmp_path, ["source.py"], tmp_path, deadline=time.monotonic() - 1.0
    )

    assert result.returncode == 1
    assert "budget" in result.stderr


def test_no_deadline_keeps_the_legacy_per_batch_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Direct unit callers pass no deadline; they must not silently get zero."""
    seen: list[float] = []

    def record(*_a: object, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(float(kwargs["timeout_seconds"]))
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(policy, "_semgrep_target_batches", lambda targets, _root: [targets])
    monkeypatch.setattr(policy, "_run_command", record)
    monkeypatch.setattr(policy, "_verify_semgrep_targets", lambda result, *_a: result)

    policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert seen == [float(policy.SEMGREP_TIMEOUT_SECONDS)]


def test_the_watchdog_arms_only_in_a_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole-process bound, and the control that it is conditional.

    `_container_clamped` bounds a child. Review on PR #5319 named three places
    the work is not a child and no deadline reached it: `changed_from_git`
    shells out unbounded, the import graph is built in-process, and this
    module's own path discovery and tree materialization run before its
    aggregate clock starts. The watchdog goes around the process instead of
    around each of them.
    """
    armed: list[float] = []

    class FakeTimer:
        daemon = False

        def __init__(self, interval: float, _fn: object) -> None:
            armed.append(interval)

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(policy.threading, "Timer", FakeTimer)

    monkeypatch.setitem(
        sys.modules,
        "run_workflow_local_test",
        _detector(in_container=False),
    )
    assert policy._arm_container_watchdog("pytest") is None
    assert armed == [], "the watchdog armed outside a container"

    monkeypatch.setitem(
        sys.modules,
        "run_workflow_local_test",
        _detector(in_container=True),
    )
    assert policy._arm_container_watchdog("pytest") is not None
    assert armed == [policy.CONTAINER_PROCESS_CEILING_SECONDS], (
        f"the watchdog armed at {armed}, not the process ceiling."
    )


def test_the_process_ceiling_sits_above_the_subprocess_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """An inner deadline must fire first, so the reader gets the useful message.

    Same ordering rule as ADR-086 item 9. If these were equal the watchdog
    could win the race and report "look at selection and setup" for a hang that
    was a subprocess exceeding its own budget.
    """
    assert policy.CONTAINER_PROCESS_CEILING_SECONDS > policy.CONTAINER_SUBPROCESS_CEILING_SECONDS
