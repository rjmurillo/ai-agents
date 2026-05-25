"""Tests for wait_for_unresolved_zero.py (REQ-012-01, REQ-012-02 revised).

Pins the four AC scenarios from REQ-012-02 (revised per /plan ceremony):

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
    """REQ-012-02 AC 1: bot-settle detection."""

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
    """REQ-012-02 AC 2: incomplete pagination is not a valid zero observation."""

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
    """REQ-012-02 AC 3: max-wait timeout exits with settled=false."""

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
    """REQ-012-02 AC 4 (revised): two zeros inside the interval count as one.

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
    """REQ-012-01 AC: invalid CLI args return exit code 2 (config error)."""

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


class JsonContractStdoutTest(unittest.TestCase):
    """Issue #2069 Finding A: invalid-arg JSON payloads emit to stdout.

    Stdout-parsing callers expect every outcome (success, timeout, config
    error) to surface a JSON object on stdout. The earlier behavior
    routed invalid-arg failures to stderr only, breaking parsers that
    consumed `subprocess.run(..., capture_output=True).stdout`. The
    canonical CLI contract is "JSON to stdout, human noise to stderr."
    """

    def _capture(self, argv: list[str]) -> tuple[int, str, str]:
        """Run main(argv) and return (exit_code, stdout, stderr)."""
        import io
        import contextlib

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = wfz.main(argv)
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_negative_pull_request_emits_json_to_stdout(self) -> None:
        """POSITIVE: invalid pull_request yields JSON failure payload on stdout."""
        rc, stdout, _ = self._capture(["--pull-request", "-1"])
        self.assertEqual(rc, 2)
        # Stdout MUST contain a parseable JSON object with settled=false.
        payload = json.loads(stdout)
        self.assertFalse(payload.get("settled", True))
        self.assertIn("positive", (payload.get("reason") or "").lower())

    def test_zero_pull_request_emits_json_to_stdout(self) -> None:
        """POSITIVE: pull_request=0 yields JSON failure payload on stdout."""
        rc, stdout, _ = self._capture(["--pull-request", "0"])
        self.assertEqual(rc, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload.get("settled", True))

    def test_zero_interval_emits_json_to_stdout(self) -> None:
        """POSITIVE: interval=0 yields JSON failure payload on stdout."""
        rc, stdout, _ = self._capture(
            ["--pull-request", "1", "--interval-seconds", "0"],
        )
        self.assertEqual(rc, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload.get("settled", True))
        self.assertIn("interval", (payload.get("reason") or "").lower())

    def test_zero_max_wait_emits_json_to_stdout(self) -> None:
        """POSITIVE: max-wait=0 yields JSON failure payload on stdout."""
        rc, stdout, _ = self._capture(
            ["--pull-request", "1", "--max-wait-seconds", "0"],
        )
        self.assertEqual(rc, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload.get("settled", True))

    def test_negative_pull_request_stderr_has_no_json(self) -> None:
        """NEGATIVE: stderr MUST NOT carry the JSON payload (single channel)."""
        _, _, stderr = self._capture(["--pull-request", "-1"])
        # A short human notice on stderr is allowed; a JSON object is not.
        # Look for the JSON braces; their absence is the load-bearing claim.
        self.assertNotIn('"settled":', stderr)
        self.assertNotIn('"observations":', stderr)


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
    """Pin the 3-reading requirement per REQ-012-01 revised AC."""

    def test_constant_is_three(self) -> None:
        self.assertEqual(wfz.REQUIRED_CONSECUTIVE_ZEROS, 3)


class StrictPaginationFlagTest(unittest.TestCase):
    """PR #1989 copilot/coderabbit: BooleanOptionalAction must allow opt-out."""

    def test_default_strict_pagination_is_true(self) -> None:
        """POSITIVE: omitting the flag yields strict_pagination=True."""
        args = wfz._build_parser().parse_args(["--pull-request", "42"])
        self.assertTrue(args.strict_pagination)

    def test_no_strict_pagination_disables(self) -> None:
        """NEGATIVE: --no-strict-pagination must flip the flag to False."""
        args = wfz._build_parser().parse_args(
            ["--pull-request", "42", "--no-strict-pagination"],
        )
        self.assertFalse(args.strict_pagination)

    def test_explicit_strict_pagination_is_true(self) -> None:
        """POSITIVE: explicit --strict-pagination matches the default."""
        args = wfz._build_parser().parse_args(
            ["--pull-request", "42", "--strict-pagination"],
        )
        self.assertTrue(args.strict_pagination)


class ExitCodePropagationTest(unittest.TestCase):
    """PR #1989 copilot/coderabbit: ADR-035 exit codes propagate via main()."""

    def _run_main_with_runner(self, runner: Any) -> int:
        """Run main() with subprocess.run replaced by `runner` and time mocked.

        Patches `wfz.time.monotonic` directly so the default `clock` arg
        captured at def time of wait_for_settled_zero sees the mocked time.
        """
        t = [0.0]

        def fake_monotonic() -> float:
            v = t[0]
            t[0] += 200.0  # Advance > interval per call
            return v

        with mock.patch.object(wfz.subprocess, "run", side_effect=runner), \
             mock.patch.object(wfz.time, "monotonic", side_effect=fake_monotonic), \
             mock.patch.object(wfz.time, "sleep", return_value=None):
            return wfz.main(
                [
                    "--pull-request", "42",
                    "--interval-seconds", "1",
                    "--max-wait-seconds", "3",
                ],
            )

    def test_auth_error_propagates_as_exit_4(self) -> None:
        """POSITIVE: underlying exit 4 -> main returns 4."""
        runner, _ = _make_runner(
            [{"unresolved_count": 0, "fetched_pages_complete": False}],
            exit_codes=[4],
        )
        # Provide enough payloads to fail max-wait (runner runs once
        # then runner() will be called again; provide a second item).
        runner2, _ = _make_runner(
            [{"unresolved_count": 0, "fetched_pages_complete": False}] * 5,
            exit_codes=[4] * 5,
        )
        rc = self._run_main_with_runner(runner2)
        self.assertEqual(rc, 4)

    def test_config_error_propagates_as_exit_2(self) -> None:
        """POSITIVE: underlying exit 2 -> main returns 2."""
        runner, _ = _make_runner(
            [{"unresolved_count": 0, "fetched_pages_complete": False}] * 5,
            exit_codes=[2] * 5,
        )
        rc = self._run_main_with_runner(runner)
        self.assertEqual(rc, 2)

    def test_logic_failure_remains_exit_1(self) -> None:
        """NEGATIVE: underlying exit 0 + no settle -> main returns 1."""
        runner, _ = _make_runner(
            [{"unresolved_count": 5, "fetched_pages_complete": True}] * 5,
            exit_codes=[0] * 5,
        )
        rc = self._run_main_with_runner(runner)
        self.assertEqual(rc, 1)


class CoverageCompleterTests(unittest.TestCase):
    """Cover branches that the main scenarios miss, to hit 100% block + branch.

    PR #1989 user requirement: tests must catch the bugs that bot reviewers
    caught. Branches like "underlying script missing" and "pull_request <= 0
    in wait_for_settled_zero directly" need explicit exercise.
    """

    def test_wait_for_settled_zero_rejects_non_positive_pull_request(self) -> None:
        """Direct call with PR <= 0 returns _failure, not main()."""
        result = wfz.wait_for_settled_zero(
            pull_request=0, interval_seconds=180, max_wait_seconds=1200,
        )
        self.assertFalse(result["settled"])
        self.assertIn("positive", (result.get("reason") or "").lower())

    def test_wait_for_settled_zero_handles_missing_underlying_script(self) -> None:
        """When _resolve_underlying_script returns a non-file path, fail clean.

        Pinned per PR #1989 review (copilot): the synthetic observation MUST honor the
        documented schema (`timestamp: float`). Record the resolved clock
        value, never None, so downstream consumers never special-case the type.
        """
        from pathlib import Path as _Path

        with mock.patch.object(
            wfz,
            "_resolve_underlying_script",
            return_value=_Path("/definitely/not/here.py"),
        ):
            result = wfz.wait_for_settled_zero(
                pull_request=42,
                interval_seconds=180,
                max_wait_seconds=1200,
                runner=lambda *_a, **_kw: mock.Mock(returncode=0, stdout="{}"),
                clock=lambda: 1234.5,
                sleeper=lambda _s: None,
            )
        self.assertFalse(result["settled"])
        self.assertIn("missing", (result.get("reason") or "").lower())
        observations = result.get("observations") or []
        self.assertEqual(len(observations), 1)
        timestamp = observations[0].get("timestamp")
        self.assertIsInstance(timestamp, float)
        self.assertEqual(timestamp, 1234.5)

    def test_sleep_seam_real_no_op_path(self) -> None:
        """Call _sleep(0) so the module-level body is covered."""
        # _sleep(0) should return None without raising.
        self.assertIsNone(wfz._sleep(0))

    def test_now_seam_real_path(self) -> None:
        """Call _now() so the module-level body is covered."""
        v1 = wfz._now()
        self.assertIsInstance(v1, float)

    def test_failure_helper_shape(self) -> None:
        """_failure returns the documented dict shape."""
        result = wfz._failure("reason", 42, [{"ts": 1}])
        self.assertEqual(result["pull_request"], 42)
        self.assertEqual(result["reason"], "reason")
        self.assertFalse(result["settled"])
        self.assertFalse(result["success"])

    def test_main_invalid_pull_request_argv_value(self) -> None:
        """argparse rejects non-integer pull_request; main catches SystemExit
        and returns exit code 2 instead of propagating.

        PR #2070 follow-up: parse-level argparse failures (bad type, missing
        required arg, unknown flag) now emit JSON to stdout and return 2,
        preserving the single-channel JSON stdout contract for every outcome.
        """
        import contextlib
        import io
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(io.StringIO()):
            rc = wfz.main(["--pull-request", "abc"])
        self.assertEqual(rc, 2)
        payload = json.loads(out_buf.getvalue())
        self.assertFalse(payload["settled"])
        self.assertEqual(payload["reason"], "invalid CLI arguments")

    def test_main_missing_required_arg_emits_json_to_stdout(self) -> None:
        """argparse missing-required-arg failure produces JSON on stdout.

        PR #2070 Copilot review thread: stdout-parsing callers must see a
        parseable JSON payload even when argparse rejects the invocation
        before main() can run its own validation.
        """
        import contextlib
        import io
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = wfz.main([])
        self.assertEqual(rc, 2)
        payload = json.loads(out_buf.getvalue())
        self.assertFalse(payload["settled"])
        # stderr carries a short human message, not the JSON payload.
        self.assertNotIn('"settled":', err_buf.getvalue())

    def test_main_unknown_flag_emits_json_to_stdout(self) -> None:
        """argparse unknown-flag failure produces JSON on stdout (exit 2)."""
        import contextlib
        import io
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(io.StringIO()):
            rc = wfz.main(["--bogus-flag"])
        self.assertEqual(rc, 2)
        payload = json.loads(out_buf.getvalue())
        self.assertFalse(payload["settled"])

    def test_main_returns_zero_when_settled(self) -> None:
        """POSITIVE: main returns 0 when wait_for_settled_zero settles."""
        t = [0.0]

        def fake_monotonic() -> float:
            v = t[0]
            t[0] += 200.0
            return v

        # Three consecutive zeros with complete=True => settle.
        payloads = [{"unresolved_count": 0, "fetched_pages_complete": True}] * 5
        runner, _ = _make_runner(payloads, exit_codes=[0] * 5)

        with mock.patch.object(wfz.subprocess, "run", side_effect=runner), \
             mock.patch.object(wfz.time, "monotonic", side_effect=fake_monotonic), \
             mock.patch.object(wfz.time, "sleep", return_value=None):
            rc = wfz.main(
                [
                    "--pull-request", "42",
                    "--interval-seconds", "1",
                    "--max-wait-seconds", "3600",
                ],
            )
        self.assertEqual(rc, 0)

    def test_main_handles_empty_observations(self) -> None:
        """NEGATIVE: when result.observations is empty, default exit 1."""
        with mock.patch.object(
            wfz,
            "wait_for_settled_zero",
            return_value={"settled": False, "observations": [], "reason": "x", "pull_request": 1},
        ):
            rc = wfz.main(
                [
                    "--pull-request", "1",
                    "--interval-seconds", "1",
                    "--max-wait-seconds", "1",
                ],
            )
        self.assertEqual(rc, 1)

    def test_main_handles_obs_missing_underlying_exit_code(self) -> None:
        """NEGATIVE: when no obs dict has underlying_exit_code, default 1."""
        with mock.patch.object(
            wfz,
            "wait_for_settled_zero",
            return_value={
                "settled": False,
                "observations": [{"timestamp": 0.0}],  # no underlying_exit_code key
                "reason": "x",
                "pull_request": 1,
            },
        ):
            rc = wfz.main(
                [
                    "--pull-request", "1",
                    "--interval-seconds", "1",
                    "--max-wait-seconds", "1",
                ],
            )
        self.assertEqual(rc, 1)


class InvokeUnderlyingErrorHandlingTest(unittest.TestCase):
    """PR #1989 gemini: _invoke_underlying must degrade on subprocess errors."""

    def test_file_not_found_returns_config_sentinel(self) -> None:
        """POSITIVE: missing underlying script -> exit_code 2 (config)."""
        def runner(*_args: Any, **_kw: Any) -> Any:
            raise FileNotFoundError("script missing")

        count, complete, exit_code = wfz._invoke_underlying(
            Path("/nonexistent.py"), 42, "", "", runner=runner,
        )
        self.assertEqual((count, complete, exit_code), (-1, False, 2))

    def test_timeout_returns_logic_sentinel(self) -> None:
        """POSITIVE: subprocess.TimeoutExpired -> exit_code 1 (logic)."""
        from subprocess import TimeoutExpired

        def runner(*_args: Any, **_kw: Any) -> Any:
            raise TimeoutExpired(cmd="x", timeout=60)

        count, complete, exit_code = wfz._invoke_underlying(
            Path("/p.py"), 42, "", "", runner=runner,
        )
        self.assertEqual((count, complete, exit_code), (-1, False, 1))

    def test_os_error_returns_config_sentinel(self) -> None:
        """POSITIVE: OSError (e.g. permission, EMFILE) -> exit_code 2."""
        def runner(*_args: Any, **_kw: Any) -> Any:
            raise OSError(13, "Permission denied")

        count, complete, exit_code = wfz._invoke_underlying(
            Path("/p.py"), 42, "", "", runner=runner,
        )
        self.assertEqual((count, complete, exit_code), (-1, False, 2))

    def test_malformed_json_returns_negative_count(self) -> None:
        """NEGATIVE: stdout that isn't JSON -> count=-1, exit_code preserved."""
        def runner(*_args: Any, **_kw: Any) -> Any:
            return mock.Mock(returncode=0, stdout="not json", stderr="")

        count, complete, exit_code = wfz._invoke_underlying(
            Path("/p.py"), 42, "", "", runner=runner,
        )
        self.assertEqual((count, complete, exit_code), (-1, False, 0))

    def test_malformed_payload_shape_returns_negative(self) -> None:
        """NEGATIVE: JSON has unresolved_count of wrong type -> count=-1."""
        def runner(*_args: Any, **_kw: Any) -> Any:
            payload = json.dumps({"unresolved_count": "not-an-int"})
            return mock.Mock(returncode=0, stdout=payload, stderr="")

        count, complete, exit_code = wfz._invoke_underlying(
            Path("/p.py"), 42, "", "", runner=runner,
        )
        self.assertEqual((count, complete, exit_code), (-1, False, 0))

    def test_non_dict_payload_returns_negative(self) -> None:
        """NEGATIVE: JSON is valid but not a dict (null/list/scalar) -> count=-1.

        PR #1989 coderabbit njY: json.loads can return non-dict types;
        calling .get() on them raises AttributeError. Defensive isinstance
        check returns the sentinel cleanly.
        """
        for payload_str in ("null", "[]", '"a string"', "42"):
            # PR #1989 coderabbit t4J: bind payload_str at definition
            # time via a default argument; otherwise the closure
            # captures the loop variable by reference and every
            # iteration runs against the last value.
            def runner(*_args: Any, _payload_str: str = payload_str, **_kw: Any) -> Any:
                return mock.Mock(returncode=0, stdout=_payload_str, stderr="")
            count, complete, exit_code = wfz._invoke_underlying(
                Path("/p.py"), 42, "", "", runner=runner,
            )
            self.assertEqual(
                (count, complete, exit_code),
                (-1, False, 0),
                f"payload {payload_str!r} should yield (-1, False, 0)",
            )


if __name__ == "__main__":
    unittest.main()
