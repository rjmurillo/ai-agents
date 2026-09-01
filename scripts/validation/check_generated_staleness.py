#!/usr/bin/env python3
"""Gate: generated output is stale relative to its sources.

CI has asked this question since REQ-003-005. The canonical CI source is
``.github/workflows/validate-generated-agents.yml``, step "Build-all staleness
check (REQ-003-005)", which runs verbatim::

    uv run python build/scripts/build_all.py --check

and step "Plugin lib sync check (M7-T1)", which runs verbatim::

    uv run python scripts/sync_plugin_lib.py --check

``scripts/validation/pre_pr.py`` ran neither. Its only ``build_all.py``
reference was ``validate_no_orphaned_build_deferrals``, which reads the
deferral comments inside that file's source and says nothing about whether the
generated tree matches its inputs. Those are different questions, so a
hand-edit to a generated file passed every local gate and failed in CI.

Measured cost on PR #5059: round-cap wiring was hand-edited into
``src/copilot-cli/skills/pr-autofix/SKILL.md``, which is generated from
``.claude/commands/pr-autofix.md``. 26 of 26 skill tests passed,
``build/generate_agents.py --validate`` passed (a different generator pair that
does not cover skills), and ``pre_pr.py`` reported unrelated findings only. CI
then showed the generator stripping all 43 lines of the wiring. The feature
would have merged as a silent no-op. Issue #5079.

Order is the contract, not a call
---------------------------------

``.claude/rules/generated-artifacts.md`` ("Generator order: sync before build")
requires ``scripts/sync_plugin_lib.py`` to run before
``build/scripts/build_all.py``. ``build_all.py`` reads ``.claude/lib/`` and
never populates it, so a change under ``scripts/github_core/`` reaches
``src/copilot-cli/lib/`` only once the sync has run. Run in the other order,
both scripts exit 0 and there is no local signal at all.

This gate honors that order and stops at the first failure. A stale
``.claude/lib/`` makes ``build_all --check`` compare the Copilot mirror against
input that is itself out of date, so its verdict carries no information until
the sync check is clean. Reporting the sync failure alone is the honest result,
and the examined count says so.

The rule also forbids resolving this by having ``build_all.py`` invoke
``sync_plugin_lib.py``: REQ-003-010 bars generators from writing under
``.claude/``, and the sync writes there by design. Both scripts run here in
``--check`` mode, which is read-only. ``build_all.py --check`` snapshots and
restores the trees it owns (issue #2440), and ``sync_plugin_lib.py --check`` is
a dry run.

Stricter/looser/different than canonical: CI runs the two checks as separate
steps and in the opposite order (build_all at line 158, sync at line 209),
which is safe there because each step reports independently. This gate runs
them in one process in the rule's order so the first reported failure is the
one a contributor must fix first.

Bounded deadlines with cleanup-preserving termination
-----------------------------------------------------

``build_all.py --check`` is read-only only because its ``finally`` at
``build/scripts/build_all.py:1123-1128`` restores the generated trees it
snapshotted. ``subprocess.run(timeout=...)`` kills with SIGKILL, which never
runs that block, so a kill landing mid-write leaves partial generated writes
in the caller's worktree (reproduced: 15 dirty paths when killed at the first
observed generated write). An unbounded child is not acceptable either: a
hung generator would stall ``pre_pr.py`` indefinitely for every caller that
is not under the lefthook job cap.

Both constraints are honored by terminating gracefully on deadline: on
expiry the child receives SIGINT, which Python surfaces as
``KeyboardInterrupt``, so the ``finally`` runs and the snapshot is restored;
only if the child ignores that for ``_TERMINATION_GRACE_SECONDS`` does the
kill escalate, with an explicit warning that the tree may hold partial
generated writes. Expiry reports EXTERNAL (exit 3): the tree was never
scored.

The budget is one aggregate for the whole gate, not per row, so the gate's
worst case is bounded below the process cap that contains it: a lefthook cap
kill lands on the whole process tree without the SIGINT path, so the gate must
be done well before the job it runs inside is. The rule is
``_GATE_BUDGET_SECONDS + _TERMINATION_GRACE_SECONDS <= cap / 2``, leaving the
other half for the rest of the sequence.

The cap itself is deliberately not restated here. An earlier revision of this
paragraph quoted ``timeout: 15m (900s)`` and a 450s worst case; both were
correct when written and both were wrong within a day of the cap moving to 4m,
because prose beside a number is a copy nobody runs.
``tests/validation/test_check_generated_staleness_termination.py`` reads the
cap out of the live ``lefthook.yml`` and asserts the inequality, so the numbers
have exactly one home and this text explains the rule rather than restating
them.

The static split alone cannot guarantee the SIGINT deadline fires first: the
gate's clock starts when the sequence reaches it, after every earlier
validation has already spent part of the same outer timer (review round 5).
So the lefthook job also declares the cap it runs under via
``PRE_PR_OUTER_CAP_SECONDS``, and the gate clamps its deadline to the
process's remaining share of that cap, minus the termination grace. If the
earlier validations left less time than one child needs, the gate reports
EXTERNAL without spawning rather than let the outer SIGKILL land mid-write.
The clamp is opt-in by environment on purpose: only the lefthook job knows
it is running under that timer, and a library caller such as pytest imports
this module long before calling it, so an unconditional wall-clock clamp
keyed to import time would misfire there. With the variable unset the
aggregate budget stands alone. ``_PROCESS_START`` is captured at module
import, which under ``pre_pr.py`` happens during process startup because the
sequence registry imports its validators up front; the seconds of skew
against the true process start are noise next to the 30s grace.

Exit codes (ADR-035):
    0 - Success (no staleness detected)
    1 - Logic error (a generator check failed: staleness or a child-reported
        error; the child's own output, echoed above the verdict, names which)
    2 - Config error (invalid repository root, or a checked script is absent)
    3 - External error (a bounded child was killed on deadline expiry)

The gate does not subdivide child exit codes further on purpose: the child
contracts are ambiguous at this boundary (``build_all.py`` uses 2 for both
configuration errors and staleness; ``sync_plugin_lib.py`` uses 1 for
missing, unreadable, and drifted sources alike), so any per-cause mapping
here would assert precision the children do not provide. The echoed child
output is the discriminator, and the failure message says so.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from enum import IntEnum
from pathlib import Path


class _Status(IntEnum):
    """Gate outcome. The value is the ADR-035 exit code, so the CLI returns
    ``int(status)`` and there is no second mapping table to drift from the
    exit-code table in the module docstring."""

    OK = 0
    DRIFT = 1
    CONFIG = 2
    EXTERNAL = 3


# Ordered per .claude/rules/generated-artifacts.md "Generator order: sync
# before build". Each row is (label, repo-relative script path). Changing the
# order breaks the contract this module exists to honor.
_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sync_plugin_lib.py --check", ("scripts", "sync_plugin_lib.py")),
    ("build_all.py --check", ("build", "scripts", "build_all.py")),
)

# One aggregate budget for the whole gate, shared across the rows, sized for
# a loaded machine per ci-scripts.md MUST 16 (measured standalone: ~4.4s for
# build_all, ~1s for sync, re-measured at 1s on a 4-CPU container) while
# fitting inside the outer lefthook cap with room for cleanup and the rest of
# the sequence (module docstring). A test pins budget + grace against the live
# lefthook.yml cap.
#
# Was 420s, a 100x margin over the work. That margin was not free: budget plus
# grace must fit in half the outer cap, so it held `pre-pr-validation` at a 15m
# cap and put 900s of a declared worst case behind a gate that runs in a second.
# 60s keeps roughly 12x headroom, at the top of the 9x to 15x in-hook inflation
# MUST-16 records for this graph, and lets the cap fall to 4m. An intermediate
# revision of this comment described 120s and a 3m cap and outlived both.
_GATE_BUDGET_SECONDS = 60.0

# How long a child gets to honor SIGINT and finish its cleanup before the
# kill escalates. build_all's restore is file copies measured in fractions of
# a second; 30s is generous without turning a hang into a long stall.
_TERMINATION_GRACE_SECONDS = 30.0

# Set by the lefthook pre-pr-validation job to the cap it runs under, in
# seconds. When present, the gate's deadline is clamped to this process's
# remaining share of that cap (module docstring, "Bounded deadlines with
# cleanup-preserving termination"). The test that parses the live
# lefthook.yml pins the declared value to the job's actual timeout.
_OUTER_CAP_ENV = "PRE_PR_OUTER_CAP_SECONDS"

# Approximates the outer timer's start; see the module docstring for why
# import time is close enough under pre_pr.py and why the clamp is opt-in.
_PROCESS_START = time.monotonic()

_MAX_OUTPUT_LINES = 40


def _decode(stream: bytes | str | None) -> str:
    """Normalize ``TimeoutExpired`` payloads, which are bytes or str by path.

    Same quirk ``scripts/validation/subprocess_runner.py`` handles for its own
    callers: the exception carries whatever the pipe held when the kill
    landed. That module's runner is not imported here because its signature
    requires a timeout, which is the one thing the ``build_all`` row must not
    have.
    """
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return stream


def _echo_tail(output: str) -> None:
    """Print the tail of a child's combined output, bounded against flooding.

    The tail, not the head. ``build_all.py`` writes several hundred lines of
    per-file generation progress to stdout and its ``STALENESS DETECTED`` block
    to stderr, so a head-bounded echo shows the progress and drops the reason.
    Callers concatenate stdout then stderr, which puts the diagnosis last.
    """
    text = output.strip()
    if not text:
        return
    lines = text.splitlines()
    if len(lines) > _MAX_OUTPUT_LINES:
        print(f"  ... {len(lines) - _MAX_OUTPUT_LINES} earlier line(s) omitted")
    for line in lines[-_MAX_OUTPUT_LINES:]:
        print(line)
    sys.stdout.flush()


def _run_check(script: Path, repo_root: Path, timeout: float) -> tuple[int | None, str]:
    """Run one generator in ``--check`` mode. Returns (exit code, output).

    A deadline expiry is an external failure, not a pass: the caller must not
    read a terminated child as a clean tree. The exit code is ``None`` on
    expiry so the caller can distinguish "the child reported drift" from "the
    child was never allowed to finish". Partial output the child already
    flushed is preserved with the expiry marker appended, not discarded.

    Termination is graceful on purpose (module docstring, "Bounded deadlines
    with cleanup-preserving termination"): SIGINT first so the child's
    ``finally`` blocks run, kill only after the grace window, with a warning
    that the tree may then hold partial generated writes. On non-POSIX hosts
    ``terminate()`` stands in for SIGINT.
    """
    proc = subprocess.Popen(
        [sys.executable, str(script), "--check"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired as exc:
        partial = _decode(exc.stdout) + _decode(exc.stderr)
        if os.name == "posix":
            proc.send_signal(signal.SIGINT)
        else:
            proc.terminate()
        try:
            late_out, late_err = proc.communicate(timeout=_TERMINATION_GRACE_SECONDS)
            partial += _decode(late_out) + _decode(late_err)
            cleanup_note = "child honored the interrupt and finished cleanup"
        except subprocess.TimeoutExpired:
            proc.kill()
            late_out, late_err = proc.communicate()
            partial += _decode(late_out) + _decode(late_err)
            cleanup_note = (
                "child ignored the interrupt and was killed; the tree may "
                "hold partial generated writes, check git status"
            )
        return None, (partial + f"\n{script.name} --check exceeded {timeout}s ({cleanup_note})")


def _remaining(deadline: float) -> float:
    """Seconds left before the gate's aggregate deadline."""
    return deadline - time.monotonic()


def _clamped_budget(now: float) -> float:
    """The aggregate budget, clamped to the outer cap's remainder when set.

    A malformed value warns and disables the clamp instead of failing: the
    clamp is a tightening of an already-bounded gate, so a typo in a hook
    configuration must not block every contributor's push. The warning is
    the loud part; the aggregate budget still bounds the gate.
    """
    raw = os.environ.get(_OUTER_CAP_ENV)
    if raw is None:
        return _GATE_BUDGET_SECONDS
    try:
        outer_cap = float(raw)
    except ValueError:
        print(
            f"[WARN] {_OUTER_CAP_ENV}={raw!r} is not a number; the outer-cap"
            f" clamp is disabled for this run and the aggregate"
            f" {_GATE_BUDGET_SECONDS}s budget stands alone.",
            file=sys.stderr,
        )
        return _GATE_BUDGET_SECONDS
    outer_remaining = outer_cap - (now - _PROCESS_START) - _TERMINATION_GRACE_SECONDS
    return min(_GATE_BUDGET_SECONDS, outer_remaining)


def check_generated_staleness(repo_root: Path) -> _Status:
    """Return the gate outcome for ``repo_root``.

    Fails closed when a checked script is absent, and reports that as CONFIG
    rather than DRIFT: an absent script means the gate could not run and the
    script needs restoring, where the drift remedy (regenerate and commit)
    would be the wrong action. A silent skip would defeat the point of
    registering the gate.

    Prints the examined count next to the failure count so a caller can tell
    "no drift across two checks" from "nothing was checked"
    (.claude/rules/ci-scripts.md MUST 11 and MUST 12).
    """
    examined = 0
    start = time.monotonic()
    deadline = start + _clamped_budget(start)
    for label, parts in _CHECKS:
        budget = _remaining(deadline)
        if budget <= 0:
            print(
                f"[FAIL] gate deadline reached before {label} ran; the tree"
                f" was never scored. The deadline is the aggregate budget"
                f" ({_GATE_BUDGET_SECONDS}s), clamped to this process's"
                f" remaining share of the outer cap when {_OUTER_CAP_ENV} is"
                f" set. Examined {examined} of {len(_CHECKS)} checks.",
                file=sys.stderr,
            )
            return _Status.EXTERNAL
        script = repo_root.joinpath(*parts)
        if not script.is_file():
            print(
                f"[ERROR] {script} is absent; the generated-staleness gate "
                f"cannot run. Examined {examined} of {len(_CHECKS)} checks.",
                file=sys.stderr,
            )
            return _Status.CONFIG

        exit_code, output = _run_check(script, repo_root, budget)
        examined += 1
        if exit_code == 0:
            continue

        # Only on failure. A clean run's several hundred lines of generator
        # progress would bury every other gate's output in pre_pr.py.
        _echo_tail(output)
        remaining = len(_CHECKS) - examined
        unrun = (
            f" The remaining {remaining} check(s) did not run: their input is not yet known good."
            if remaining
            else ""
        )
        if exit_code is None:
            print(
                f"[FAIL] {label} was killed on timeout; the tree was never "
                f"scored. Examined {examined} of {len(_CHECKS)} checks.{unrun}",
                file=sys.stderr,
            )
            return _Status.EXTERNAL
        print(
            f"[FAIL] {label} failed (exit {exit_code}). "
            f"Examined {examined} of {len(_CHECKS)} checks.{unrun}",
            file=sys.stderr,
        )
        print(
            "Read the check's output above for the cause. If it reports"
            " staleness or drift, regenerate and commit:\n"
            "  uv run python scripts/sync_plugin_lib.py\n"
            "  uv run python build/scripts/build_all.py\n"
            "Otherwise fix the error the check itself reported; regenerating"
            " is not the remedy for a configuration or source failure.",
            file=sys.stderr,
        )
        return _Status.DRIFT

    elapsed = time.monotonic() - start
    print(
        f"generated staleness: 0 stale in {examined} generator check(s)"
        f" examined ({elapsed:.1f}s of {_GATE_BUDGET_SECONDS:.0f}s budget)"
    )
    return _Status.OK


def validate_generated_staleness(repo_root: Path) -> bool:
    """Registry entry point for ``pre_pr_sequence``.

        Canonical source of the consumed contract:
        ``scripts/validation/pre_pr_sequence.py``, function ``_root_only``
        (line 162 as of this writing; the name is the durable handle, the
        number drifts and did, from 147, while this docstring still cited it).
        Its adapter signature reads verbatim below, quoted at column 0 so the
        96-character original is reproduced byte for byte rather than gaining
        an indent this docstring would have added:

def _root_only(validator: Callable[[Path], bool]) -> Callable[[Path, argparse.Namespace], bool]:

        So the registry accepts exactly ``Callable[[Path], bool]``. Different than
        canonical: this module's own CLI keeps the richer ``_Status``, because
        ADR-035 distinguishes drift (1) from a missing script (2) and a killed
        child (3) and a boolean cannot carry that. The narrowing happens here and
        nowhere else, so the registry stays uniform while the CLI stays honest.
    """
    return check_generated_staleness(repo_root) is _Status.OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return int(_Status.CONFIG)
    return int(check_generated_staleness(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
