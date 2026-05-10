"""Tests for wait_for_unresolved_zero.py (REQ-009-01, REQ-009-02 revised).

Pins the four AC scenarios from REQ-009-02 (revised per /plan ceremony):

1. Bot-settle: stubbed sequence [0, 3, 0, 0, 0] does not settle until
   the third consecutive zero is observed.
2. fetched_pages_complete=false rejection: a first zero reading with
   incomplete pagination must NOT count toward the streak.
3. Max-wait timeout: when readings stay non-zero, the wrapper exits
   with settled=false after max_wait_seconds elapses.
4. Interval-floor: two zero readings inside the interval window count
   as one, not two.

Tests inject test seams (`runner`, `clock`, `sleeper`) so no live HTTP
or wall-clock sleep occurs. Time is mocked via a monotonic counter that
advances by interval_seconds per simulated sleep.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"
sys.path.insert(0, str(SCRIPT_DIR))

import wait_for_unresolved_zero as wfz  # noqa: E402


def _make_runner(payloads: list[dict], exit_codes: list[int] | None = None):
    """Return a subprocess.run double yielding the given JSON payloads in order.

    Each call returns a mock CompletedProcess whose `stdout` is the
    JSON-serialized next payload and whose `returncode` is the next
    exit code (default 0).
    """
    if exit_codes is None:
        exit_codes = [0] * len(payloads)
    if len(exit_codes) != len(payloads):
        raise ValueError("exit_codes length must match payloads length")
    state = {"i": 0}

    def runner(*args: Any, **kwargs: Any) -> Any:
        i = state["i"]
        if i >= len(payloads):
            # Pad with the last payload so an over-eager loop fails loudly
            # in the assertion, not via IndexError here.
            payload = payloads[-1]
            code = exit_codes[-1]
        else:
            payload = payloads[i]
            code = exit_codes[i]
        state["i"] = i + 1
        return mock.Mock(
            stdout=json.dumps(payload),
            stderr="",
            returncode=code,
        )

    return runner, state


def _make_clock_and_sleeper(interval_seconds: int):
    """Return (clock, sleeper) pair where sleeper advances clock by `interval_seconds`."""
    state = {"t": 0.0}

    def clock() -> float:
        return state["t"]

    def sleeper(seconds: float) -> None:
        state["t"] += float(seconds)

    return clock, sleeper, state


class BotSettleScenarioTest(unittest.TestCase):
    """REQ-009-02 AC 1: bot-settle detection."""

    def test_does_not_settle_until_third_consecutive_zero(self) -> None:
        """Sequence [0, 3, 0, 0, 0] settles only after the third zero.

        Reading 1: 0 -> streak=1
        Reading 2: 3 -> streak reset to 0
        Reading 3: 0 -> streak=1
        Reading 4: 0 -> streak=2
        Reading 5: 0 -> streak=3 -> settle.
        """
        payloads = [
            {"unresolved_count": 0, "fetched_pages_complete": True},
            {"unresolved_count": 3, "fetched_pages_complete": True},
            {"unresolved_count": 0, "fetched_pages_complete": True},
            {"unresolved_count": 0, "fetched_pages_complete": True},
            {"unresolved_count": 0, "fetched_pages_complete": True},
        ]
        runner, state = _make_runner(payloads)
        clock, sleeper, _ = _make_clock_and_sleeper(180)

        result = wfz.wait_for_settled_zero(
            pull_request=1234,
            interval_seconds=180,
            max_wait_seconds=600,
            runner=runner,
            clock=clock,
            sleeper=sleeper,
        )

        self.assertTrue(result["settled"], result)
        self.assertEqual(state["i"], 5, "must consume exactly 5 readings")
        # The streak reset at reading 2; settlement requires 3 consecutive
        # zeros after that, hence readings 3, 4, 5.
        self.assertEqual(len(result["observations"]), 5)


class FetchedPagesCompleteRejectionTest(unittest.TestCase):
    """REQ-009-02 AC 2: incomplete pagination is not a valid zero observation."""

    def test_incomplete_pagination_does_not_count(self) -> None:
        """First reading is (0, false); must not count toward streak.

        Sequence: (0, false), (0, true), (0, true), (0, true)
        Reading 1 is incomplete -> streak stays 0.
        Readings 2, 3, 4 are complete -> streak reaches 3 -> settle.
        """
        payloads = [
            {"unresolved_count": 0, "fetched_pages_complete": False},
            {"unresolved_count": 0, "fetched_pages_complete": True},
            {"unresolved_count": 0, "fetched_pages_complete": True},
            {"unresolved_count": 0, "fetched_pages_complete": True},
        ]
        runner, state = _make_runner(payloads)
        clock, sleeper, _ = _make_clock_and_sleeper(180)

        result = wfz.wait_for_settled_zero(
            pull_request=1234,
            interval_seconds=180,
            max_wait_seconds=900,
            runner=runner,
            clock=clock,
            sleeper=sleeper,
        )

        self.assertTrue(result["settled"], result)
        self.assertEqual(state["i"], 4, "must consume exactly 4 readings")
        # The first reading appears in observations but did not count.
        self.assertFalse(
            result["observations"][0]["fetched_pages_complete"],
            "first observation should record the incomplete pagination",
        )


class MaxWaitTimeoutTest(unittest.TestCase):
    """REQ-009-02 AC 3: max-wait timeout exits with settled=false."""

    def test_timeout_exits_not_settled(self) -> None:
        """When readings stay non-zero, max_wait_seconds elapses and exits 1.

        With max_wait_seconds=10 and interval_seconds=5, the wrapper takes
        one reading per sleep cycle. After ~2 cycles the clock has elapsed
        10s; the wrapper exits with settled=false and reason populated.
        """
        # Long stream of non-zero readings so the loop never settles.
        payloads = [
            {"unresolved_count": 2, "fetched_pages_complete": True}
        ] * 100
        runner, _ = _make_runner(payloads)
        clock, sleeper, time_state = _make_clock_and_sleeper(5)

        result = wfz.wait_for_settled_zero(
            pull_request=1234,
            interval_seconds=5,
            max_wait_seconds=10,
            runner=runner,
            clock=clock,
            sleeper=sleeper,
        )

        self.assertFalse(result["settled"])
        self.assertFalse(result["success"])
        self.assertIn("max_wait_seconds", (result["reason"] or ""))
        self.assertGreaterEqual(time_state["t"], 10.0)


class IntervalFloorEnforcementTest(unittest.TestCase):
    """REQ-009-02 AC 4 (revised): two zeros inside the interval count as one.

    The interval-floor requirement is symmetric to the 3-reading requirement:
    a streak only advances when the previous counted reading was at least
    interval_seconds ago. Without this guard, the wrapper could be fooled
    by a tight burst of zeros that arrive faster than the bot scan window.
    """

    def test_zeros_inside_interval_do_not_double_count(self) -> None:
        """Compare paired runs: with floor, settlement takes more readings.

        Two scenarios driven by identical zero-streams but different
        sleeper functions:

          A) Sleeper honors the requested interval (advances by 180s):
             every reading counts; settlement at the 3rd reading
             (t=360). Observations consumed: 3.
          B) Sleeper short-cuts to half the interval (advances by 90s):
             every other reading is rejected by the gap check;
             settlement at the 5th reading (t=360). Observations
             consumed: 5.

        If the wrapper ignored the floor, scenario B would also settle
        in 3 readings. The 5-reading consumption proves the floor is
        being honored. The arrival-time math is identical between A
        and B at the settlement point (both reach t=360); only the
        number of intervening rejected observations differs.
        """
        # Scenario A: sleeper advances clock by full interval.
        payloads_a = [
            {"unresolved_count": 0, "fetched_pages_complete": True}
        ] * 100
        runner_a, state_a = _make_runner(payloads_a)
        clock_a, sleeper_a, _ = _make_clock_and_sleeper(180)
        result_a = wfz.wait_for_settled_zero(
            pull_request=1234,
            interval_seconds=180,
            max_wait_seconds=1200,
            runner=runner_a,
            clock=clock_a,
            sleeper=sleeper_a,
        )

        # Scenario B: sleeper advances clock by HALF the interval.
        payloads_b = [
            {"unresolved_count": 0, "fetched_pages_complete": True}
        ] * 100
        runner_b, state_b = _make_runner(payloads_b)
        time_state = {"t": 0.0}

        def clock_b() -> float:
            return time_state["t"]

        def sleeper_b(seconds: float) -> None:
            time_state["t"] += float(seconds) / 2.0

        result_b = wfz.wait_for_settled_zero(
            pull_request=1234,
            interval_seconds=180,
            max_wait_seconds=1200,
            runner=runner_b,
            clock=clock_b,
            sleeper=sleeper_b,
        )

        # Both must settle eventually.
        self.assertTrue(result_a["settled"])
        self.assertTrue(result_b["settled"])

        # A consumes exactly 3 readings; B consumes 5 because the floor
        # rejects the in-interval zeros. The differential is the proof
        # that the floor is being enforced.
        self.assertEqual(state_a["i"], 3, (
            "scenario A (full-interval sleeper) must settle at reading 3"
        ))
        self.assertEqual(state_b["i"], 5, (
            "scenario B (half-interval sleeper) must consume 5 readings; "
            "fewer means the floor is being skipped"
        ))


class ArgvContractTest(unittest.TestCase):
    """CWE-78: subprocess invocation uses argv vector, no shell concat."""

    def test_runner_invoked_with_argv_vector(self) -> None:
        """The runner receives a list[str], not a shell string."""
        captured: dict[str, Any] = {}

        def runner(*args: Any, **kwargs: Any) -> Any:
            captured["argv"] = args[0]
            captured["kwargs"] = kwargs
            return mock.Mock(
                stdout=json.dumps(
                    {"unresolved_count": 0, "fetched_pages_complete": True},
                ),
                stderr="",
                returncode=0,
            )

        clock, sleeper, _ = _make_clock_and_sleeper(180)
        wfz.wait_for_settled_zero(
            pull_request=42,
            interval_seconds=180,
            max_wait_seconds=900,
            owner="rjmurillo",
            repo="ai-agents",
            runner=runner,
            clock=clock,
            sleeper=sleeper,
        )

        self.assertIsInstance(captured["argv"], list)
        self.assertNotIn("shell", captured["kwargs"])
        # argv must include --pull-request as a separate token, not concatenated
        self.assertIn("--pull-request", captured["argv"])
        self.assertIn("42", captured["argv"])
        # Owner and repo passed through when provided.
        self.assertIn("--owner", captured["argv"])
        self.assertIn("rjmurillo", captured["argv"])
        self.assertIn("--repo", captured["argv"])
        self.assertIn("ai-agents", captured["argv"])


class ConfigValidationTest(unittest.TestCase):
    """REQ-009-01 AC: invalid CLI args return exit code 2 (config error)."""

    def test_negative_pull_request_exits_two(self) -> None:
        self.assertEqual(wfz.main(["--pull-request", "-1"]), 2)

    def test_zero_pull_request_exits_two(self) -> None:
        self.assertEqual(wfz.main(["--pull-request", "0"]), 2)

    def test_zero_interval_exits_two(self) -> None:
        self.assertEqual(
            wfz.main(
                ["--pull-request", "1", "--interval-seconds", "0"],
            ),
            2,
        )


class AuthErrorPropagationTest(unittest.TestCase):
    """Exit code 4 from the underlying script propagates as settle=false."""

    def test_auth_error_returns_unsettled(self) -> None:
        payloads = [{"unresolved_count": 0, "fetched_pages_complete": False}]
        runner, _ = _make_runner(payloads, exit_codes=[4])
        clock, sleeper, _ = _make_clock_and_sleeper(180)

        result = wfz.wait_for_settled_zero(
            pull_request=42,
            interval_seconds=180,
            max_wait_seconds=900,
            runner=runner,
            clock=clock,
            sleeper=sleeper,
        )
        self.assertFalse(result["settled"])
        self.assertIn("auth error", (result["reason"] or "").lower())


class RequiredConsecutiveZerosConstantTest(unittest.TestCase):
    """Pin the 3-reading requirement per REQ-009-01 revised AC."""

    def test_constant_is_three(self) -> None:
        self.assertEqual(wfz.REQUIRED_CONSECUTIVE_ZEROS, 3)


if __name__ == "__main__":
    unittest.main()
