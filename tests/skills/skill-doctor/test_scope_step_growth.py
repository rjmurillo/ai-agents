"""Scope and session work grows about linearly, measured in steps and not in seconds.

The step meter counts bytecode inside the skill's scripts, so a loaded runner cannot change
a result. Work inside one C call, such as a system call or a scan of a list, is one
instruction: a slowdown hidden there is not seen. Each bound has a control that fails it.
The synthetic repositories and the workload come from ``test_scope_scaling``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from types import CodeType
from typing import Any

import pytest
import repository_scope
from repository_scope import RepositoryScope, count_sessions_by_root, resolve_repository_scope
from session_discovery import clear_cwd_resolution_cache
from test_scope_scaling import build_world, make_sessions, match_and_count, ref_scope

_SCRIPTS = str(Path(repository_scope.__file__).parent) + os.sep
# Twice the checkouts is a little over twice the steps as shipped, and over four times when
# every selected checkout expands its common directory again. Measured on 8 and 16 checkouts:
# 2.33 times as shipped, 4.65 times for ``ref_scope``.
_CHECKOUT_GROWTH = 3.0
# Twice the sessions is twice the steps. Measured on 12 and 24 sessions: 1.77 times as
# shipped, 3.46 times when every session counts all the sessions again. The sizes are small
# because the meter is slow: the quadratic control runs about 257,000 counted steps here.
_SESSION_GROWTH = 2.2
_SESSION_COUNTS = (12, 24)


def _steps(run: Callable[[], object]) -> int:
    """Bytecode instructions the skill's scripts execute during ``run()``."""
    monitoring = sys.monitoring
    # By convention ids 0, 1, 2 and 5 belong to debuggers, coverage, profilers and optimizers.
    free = [i for i in (3, 4) if monitoring.get_tool(i) is None]
    assert free, "monitoring tool ids 3 and 4 are both taken, so the step meter cannot run"
    tool = free[0]
    count = 0

    def on_instruction(code: CodeType, _offset: int) -> None:
        nonlocal count
        if code.co_filename.startswith(_SCRIPTS):
            count += 1

    monitoring.use_tool_id(tool, "scope-step-meter")
    try:
        monitoring.register_callback(tool, monitoring.events.INSTRUCTION, on_instruction)
        monitoring.set_events(tool, monitoring.events.INSTRUCTION)
        run()
    finally:
        monitoring.set_events(tool, monitoring.events.NO_EVENTS)
        monitoring.register_callback(tool, monitoring.events.INSTRUCTION, None)
        monitoring.free_tool_id(tool)
    assert count > 0, "the meter counted nothing inside the skill's scripts"
    return count


@pytest.fixture
def worlds(tmp_path) -> Iterator[dict[int, dict[str, Any]]]:
    """One synthetic repository of 8 checkouts and one of 16.

    Built per test and not per module: a wider fixture would run git before the suite's
    per-test guards clear an inherited ``GIT_DIR``.
    """
    worlds = {}
    for checkouts in (8, 16):
        root = tmp_path / f"world-{checkouts}"
        root.mkdir()
        worlds[checkouts] = build_world(root, checkouts - 1)
    yield worlds
    clear_cwd_resolution_cache()  # leave no resolved cwd behind for a later test


def _assert_scope_steps_stay_near_double(worlds, resolve) -> None:
    small, large = (
        _steps(partial(resolve, [world["main"], *world["trees"]]))
        for world in (worlds[8], worlds[16])
    )
    assert large <= _CHECKOUT_GROWTH * small, (
        f"scope work grows too fast with checkouts for {resolve.__name__}: {small} steps "
        f"for 8 checkouts, {large} steps for 16, over the {_CHECKOUT_GROWTH} times bound"
    )


def _assert_session_steps_double(worlds, work) -> None:
    world = worlds[16]
    counts = []
    for session_count in _SESSION_COUNTS:
        clear_cwd_resolution_cache()  # each count starts cold, as a run does
        scope = resolve_repository_scope([world["main"], *world["trees"]])
        sessions = make_sessions(world, session_count)
        counts.append(_steps(partial(work, scope, sessions)))
    small, large = counts
    few, many = _SESSION_COUNTS
    assert large <= _SESSION_GROWTH * small, (
        f"session work is not linear for {work.__name__}: {small} steps for {few} sessions, "
        f"{large} steps for {many}, over the {_SESSION_GROWTH} times bound"
    )


def test_scope_steps_stay_near_double_when_the_checkouts_double(worlds):
    _assert_scope_steps_stay_near_double(worlds, resolve_repository_scope)


def test_the_checkout_bound_fails_when_every_checkout_expands_again(worlds):
    """Negative control: the same check, on logic that expands for every selected checkout."""
    # "DID NOT RAISE" below means the meter no longer sees the expansion: the check is blind.
    with pytest.raises(AssertionError, match="scope work grows too fast"):
        _assert_scope_steps_stay_near_double(worlds, ref_scope)


def test_matching_and_counting_steps_double_when_the_sessions_double(worlds):
    _assert_session_steps_double(worlds, match_and_count)


def recount_per_session(scope: RepositoryScope, sessions: list[dict[str, Any]]) -> None:
    """A controlled mutant of ``match_and_count``: every session counts all of them again."""
    for session in sessions:
        scope.matches("copilot", session["meta"])
        count_sessions_by_root(sessions, scope.paths)


def test_the_session_bound_fails_when_every_session_recounts(worlds):
    """Negative control: the same check, on a workload that is quadratic in sessions."""
    with pytest.raises(AssertionError, match="session work is not linear"):
        _assert_session_steps_double(worlds, recount_per_session)
