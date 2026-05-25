#!/usr/bin/env python3
"""Wait for a PR's unresolved thread count to settle at zero (REQ-009-01).

Polls ``get_unresolved_review_threads.py`` and exits 0 only after observing
THREE consecutive readings of ``unresolved_count == 0 AND
fetched_pages_complete == true``, each separated by at least
``--interval-seconds`` (default 180s). The pre-mortem documented in
.agents/plans/active/req-009-retro-fixes-pr-1965.md raised the original
60s/2-reading wedge to 180s/3 readings because Copilot and Devin webhooks
arrive 30-120s after a push; a 60s/2-reading window leaves a real chance
of declaring "done" mid-scan.

Canonical source: this wrapper mirrors the output contract of
``.claude/skills/github/scripts/pr/get_unresolved_review_threads.py``.
The fields it depends on, verbatim from the underlying script:

    "unresolved_count": <int>,
    "fetched_pages_complete": <bool>,

A first observation with ``fetched_pages_complete == false`` is rejected
even when ``unresolved_count == 0``: a partial fetch returning zero is
not evidence that zero unresolved threads exist (this is exactly the lie
that produced PR #1965). Three consecutive complete-and-zero readings
across the interval floor are the minimum settling proof.

Stricter/looser/different than canonical:
  - The underlying script is a one-shot snapshot. This wrapper adds the
    multi-reading settlement gate on top of it. It does not modify the
    snapshot contract.
  - The interval-floor and reading-count are NEW local discipline; there
    is no upstream "settled" signal to mirror.

Subprocess invocations use the argv vector with ``shell=False`` per
CWE-78. No string concatenation; the pull-request number is an int.

Exit codes follow ADR-035:
    0 - Settled at zero (3 consecutive zero readings observed)
    1 - Logic error (max wait elapsed without settling)
    2 - Config error (invalid argument)
    4 - Auth error (gh not authenticated; propagated from underlying script)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# How many consecutive complete-and-zero readings we require to declare
# the PR settled. Documented in REQ-009-01 revised AC. Pinned in tests.
REQUIRED_CONSECUTIVE_ZEROS = 3


def _resolve_underlying_script() -> Path:
    """Return the path to get_unresolved_review_threads.py.

    The wrapper lives next to the underlying script; we resolve by
    sibling lookup so the wrapper works whether invoked from the repo
    root, from inside the skill directory, or from a worktree.
    """
    here = Path(__file__).resolve().parent
    return here / "get_unresolved_review_threads.py"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Poll get_unresolved_review_threads.py until three consecutive "
            "complete-and-zero readings are observed, separated by at least "
            "--interval-seconds."
        ),
    )
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number (positive int).",
    )
    parser.add_argument(
        "--owner", default="", help="Repository owner (forwarded to underlying script).",
    )
    parser.add_argument(
        "--repo", default="", help="Repository name (forwarded to underlying script).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=180,
        help=(
            "Minimum seconds between consecutive observations counted toward "
            "the settlement window (default: 180)."
        ),
    )
    parser.add_argument(
        "--max-wait-seconds",
        type=int,
        default=1200,
        help="Maximum total seconds to wait before exiting 1 (default: 1200).",
    )
    # PR #1989 copilot/coderabbit: `action="store_true"` + `default=True`
    # makes the flag impossible to disable. Use BooleanOptionalAction so
    # `--strict-pagination` and `--no-strict-pagination` both work, default
    # remaining True.
    parser.add_argument(
        "--strict-pagination",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Require fetched_pages_complete == true on every counted "
            "observation (default: True; disable with --no-strict-pagination)."
        ),
    )
    return parser


def _invoke_underlying(
    script_path: Path,
    pull_request: int,
    owner: str,
    repo: str,
    runner: object | None = None,
) -> tuple[int, bool, int]:
    """Invoke the underlying script once and return (count, complete, exit_code).

    Subprocess call uses argv vector with shell=False per CWE-78. The
    ``runner`` parameter is a seam for tests; production callers leave
    it at the default ``subprocess.run``.

    PR #1989 gemini: wrap runner invocation in try/except so subprocess
    timeouts, missing binaries, or unexpected runtime errors degrade to
    a single sentinel observation (-1, False, exit_code) instead of
    crashing the polling loop. The exit_code is preserved on the
    underlying-script path (FileNotFoundError -> 2 config, TimeoutExpired
    -> 1 logic) so ADR-035 propagation downstream still works.
    """
    argv: list[str] = [
        sys.executable,
        str(script_path),
        "--pull-request",
        str(int(pull_request)),
    ]
    if owner:
        argv.extend(["--owner", owner])
    if repo:
        argv.extend(["--repo", repo])
    # Resolve runner at call time, not def time, so test-mocks of
    # `wfz.subprocess.run` take effect when callers omit `runner=`.
    if runner is None:
        runner = subprocess.run
    try:
        completed = runner(  # type: ignore[operator]
            argv,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        # Underlying script missing: config error per ADR-035.
        return (-1, False, 2)
    except subprocess.TimeoutExpired:
        # Underlying timed out: logic error per ADR-035 (the wrapper's
        # own --max-wait-seconds takes over).
        return (-1, False, 1)
    except OSError:
        # Other OS-level failure (permissions, fork failure): config.
        return (-1, False, 2)
    exit_code = getattr(completed, "returncode", 1)
    stdout = getattr(completed, "stdout", "") or ""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return (-1, False, exit_code)
    # PR #1989 coderabbit njY: json.loads can return null, list, or scalar.
    # Calling .get() on a non-dict raises AttributeError. Underlying script
    # is controlled, but defensive code is cheap and prevents future crashes.
    if not isinstance(payload, dict):
        return (-1, False, exit_code)
    try:
        count = int(payload.get("unresolved_count", -1))
        complete = bool(payload.get("fetched_pages_complete", False))
    except (TypeError, ValueError):
        # Malformed JSON shape (count not coercible to int).
        return (-1, False, exit_code)
    return (count, complete, exit_code)


def _now() -> float:
    """Monotonic clock seam (mock target in tests)."""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    """Sleep seam (mock target in tests)."""
    time.sleep(seconds)


def wait_for_settled_zero(
    pull_request: int,
    interval_seconds: int,
    max_wait_seconds: int,
    *,
    owner: str = "",
    repo: str = "",
    strict_pagination: bool = True,
    runner: object | None = None,
    clock: object | None = None,
    sleeper: object | None = None,
) -> dict:
    """Return the settlement result as a dict, regardless of outcome.

    The returned dict matches the script's stdout payload:

        {
          "success": bool,            # True only when settled
          "pull_request": int,
          "observations": [
            {"timestamp": float, "unresolved_count": int,
             "fetched_pages_complete": bool},
            ...
          ],
          "settled": bool,            # alias for success
          "reason": str | None        # populated on non-settled exit
        }

    Settlement requires ``REQUIRED_CONSECUTIVE_ZEROS`` consecutive
    observations satisfying all of:
      - ``unresolved_count == 0``
      - ``fetched_pages_complete == true`` (when strict_pagination)
      - the previous counted observation was at least
        ``interval_seconds`` ago
    """
    if pull_request <= 0:
        return _failure("pull_request must be positive", pull_request, [])

    # Resolve seams at call time so test-mocks of `wfz.subprocess.run`,
    # `wfz._now`, and `wfz._sleep` take effect when callers omit them.
    if clock is None:
        clock = _now
    if sleeper is None:
        sleeper = _sleep
    script_path = _resolve_underlying_script()
    if not script_path.is_file():
        # PR #1989 cursor zTH: missing underlying script is a config
        # error per ADR-035. Surface as exit_code=2 via a synthetic
        # observation so main() returns 2, not 1.
        #
        # PR #1989 copilot follow-up: record a real timestamp from the
        # resolved clock seam so the observation honors the documented
        # schema (`{"timestamp": float, ...}`). A null timestamp forced
        # every downstream consumer to handle a special case.
        return _failure(
            f"underlying script missing: {script_path}",
            pull_request,
            [
                {
                    "timestamp": clock(),  # type: ignore[operator]
                    "unresolved_count": -1,
                    "fetched_pages_complete": False,
                    "underlying_exit_code": 2,
                },
            ],
        )

    observations: list[dict] = []
    last_counted_at: float | None = None
    consecutive_zeros = 0
    start = clock()  # type: ignore[operator]

    while True:
        # Take one snapshot.
        count, complete, exit_code = _invoke_underlying(
            script_path, pull_request, owner, repo, runner=runner,
        )
        now = clock()  # type: ignore[operator]
        observations.append(
            {
                "timestamp": now,
                "unresolved_count": count,
                "fetched_pages_complete": complete,
                "underlying_exit_code": exit_code,
            },
        )

        # Auth or fatal upstream errors propagate.
        if exit_code == 4:
            return _failure(
                "underlying script returned auth error (exit 4)",
                pull_request,
                observations,
            )
        # PR #1989 coderabbit t4E: config errors do not heal with more
        # polling (missing gh, bad repo, malformed env). Short-circuit
        # exit 2 the same way exit 4 short-circuits, instead of waiting
        # the full max_wait_seconds before returning the same failure.
        if exit_code == 2:
            return _failure(
                "underlying script returned config error (exit 2)",
                pull_request,
                observations,
            )

        zero_and_complete = (
            count == 0 and (complete or not strict_pagination)
        )
        gap_ok = (
            last_counted_at is None
            or (now - last_counted_at) >= interval_seconds
        )
        if zero_and_complete and gap_ok:
            consecutive_zeros += 1
            last_counted_at = now
            if consecutive_zeros >= REQUIRED_CONSECUTIVE_ZEROS:
                return {
                    "success": True,
                    "settled": True,
                    "pull_request": pull_request,
                    "observations": observations,
                    "reason": None,
                }
        else:
            # Any failed observation (non-zero, incomplete, or too-close)
            # resets the streak. last_counted_at is left intact only when
            # the failure was the interval gap; otherwise it is reset so
            # the next valid observation starts a fresh streak.
            if not zero_and_complete:
                consecutive_zeros = 0
                last_counted_at = None

        elapsed = now - start
        if elapsed >= max_wait_seconds:
            return _failure(
                f"max_wait_seconds={max_wait_seconds} elapsed without settling",
                pull_request,
                observations,
            )

        # Sleep until at least one interval has passed since the last
        # counted reading. If we never counted yet, sleep one interval.
        sleeper(float(interval_seconds))  # type: ignore[operator]


def _failure(reason: str, pull_request: int, observations: list[dict]) -> dict:
    return {
        "success": False,
        "settled": False,
        "pull_request": pull_request,
        "observations": observations,
        "reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Issue #2069 Finding A: the CLI contract is single-channel JSON on
    # stdout. Earlier code emitted the failure payload to stderr on
    # invalid args while emitting success payloads to stdout, which
    # broke stdout-parsing callers (they saw an empty body and treated
    # the run as malformed). Every outcome now writes JSON to stdout;
    # stderr is reserved for the short human-readable message.
    if args.pull_request <= 0:
        failure = _failure(
            "pull_request must be positive", args.pull_request, [],
        )
        print(json.dumps(failure))
        print("error: pull_request must be positive", file=sys.stderr)
        return 2
    if args.interval_seconds <= 0 or args.max_wait_seconds <= 0:
        failure = _failure(
            "interval-seconds and max-wait-seconds must be positive",
            args.pull_request,
            [],
        )
        print(json.dumps(failure))
        print(
            "error: interval-seconds and max-wait-seconds must be positive",
            file=sys.stderr,
        )
        return 2

    result = wait_for_settled_zero(
        pull_request=args.pull_request,
        interval_seconds=args.interval_seconds,
        max_wait_seconds=args.max_wait_seconds,
        owner=args.owner,
        repo=args.repo,
        strict_pagination=args.strict_pagination,
    )
    print(json.dumps(result, indent=2))
    if result["settled"]:
        return 0
    # PR #1989 copilot/coderabbit: propagate underlying-script exit code so
    # callers distinguish auth (4) and config (2) from logic-level wait
    # failures (1). Per ADR-035 exit-code contract.
    observations = result.get("observations") or []
    last_exit = 1
    for obs in reversed(observations):
        if isinstance(obs, dict) and "underlying_exit_code" in obs:
            last_exit = int(obs["underlying_exit_code"])
            break
    if last_exit == 4:
        return 4  # Auth error from underlying
    if last_exit == 2:
        return 2  # Config error from underlying
    return 1  # Default: logic/timeout


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
