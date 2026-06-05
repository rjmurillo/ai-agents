"""In-process hook dispatcher for Copilot CLI (ADR-068, addresses #2295).

Copilot CLI has no per-hook ``matcher`` support, so it runs every registered
hook entry on every tool call. With one process per matcher shim, the aggregate
Python interpreter cold-start (~200 ms each, ~40 shims) exceeds Copilot's
``preToolUse`` timeout budget and a healthy hook gets killed, denying benign
tools (false fail-closed).

This dispatcher collapses N per-shim processes into one. The host spawns a
single interpreter per event; each shim then runs *in process* via ``runpy``,
so the interpreter cold-start is paid once instead of N times.

Design contract (the security-critical part):

- **Manifest-driven, not directory-driven.** The shim list is supplied by the
  caller from the generator's registered-entry list (the same source as
  ``hooks.json``). Orphaned ``invoke_*.py`` files on disk are never executed.
- **Gate vs observe mode (ADR-068, #2342).** ``run_dispatch`` takes a
  ``short_circuit`` flag. In gate mode (``PreToolUse``) the first shim that exits
  non-zero denies the tool; the dispatcher returns that code and stops
  (fail-closed, ADR-066). A registered shim missing on disk, or an unexpected
  exception while running a shim, is a denial (exit 2), never a silent allow. A
  shim's own internal fail-open (its ``main`` returning 0 on its own error) is
  preserved, because the dispatcher only observes the shim's final exit code.
  Per-shim timeout metadata is validated, but not enforced with daemon threads:
  a timed-out Python thread cannot be killed and can leave child processes
  running after hook success. The host owns the cumulative event timeout and
  kills the whole dispatcher process if that budget is exhausted. In observe
  mode (``PostToolUse``, ``SessionStart``, ``SessionEnd``,
  ``UserPromptSubmit``) every shim runs regardless of an earlier non-zero exit;
  failures are logged and the dispatcher returns 0, matching the pre-
  consolidation host behavior where the host ran all observer entries.
- **stdin replay.** Each shim reads ``sys.stdin.buffer``; the dispatcher rewinds
  a fresh stream of the original bytes before each shim, so every shim inspects
  exactly the payload the host delivered (no #2290 schema mutation).
- **Output passthrough.** Shim stdout/stderr flows to the dispatcher's streams,
  so block guidance still reaches the host.
"""

from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path

# Hook exit-code convention (Claude/Copilot PreToolUse): 0 allow, 2 block.
ALLOW_EXIT = 0
BLOCK_EXIT = 2


def _install_stdin(raw: bytes) -> None:
    """Point ``sys.stdin`` at a fresh stream over ``raw``.

    A ``TextIOWrapper`` over a ``BufferedReader`` exposes both ``.buffer`` (read
    by the matcher-shim layer) and ``.read()``/``.isatty()`` (read by a wrapped
    original hook), so a shim and the original it wraps see the same bytes.
    """
    sys.stdin = io.TextIOWrapper(
        io.BufferedReader(io.BytesIO(raw)),
        encoding="utf-8",
        errors="strict",
    )


def _exit_code(exc: SystemExit) -> int:
    """Normalize a SystemExit code to an int (None -> 0, non-int -> 1)."""
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


def _run_shim(shim_path: Path, name: str, raw_stdin: bytes) -> int:
    """Run one shim and translate its outcome to a hook exit code."""
    _install_stdin(raw_stdin)
    try:
        runpy.run_path(str(shim_path), run_name="__main__")
        # A shim that returns without calling sys.exit allowed the tool.
        return ALLOW_EXIT
    except SystemExit as exc:
        return _exit_code(exc)
    except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory
        print(
            f"hook-dispatch: shim {name} raised "
            f"{type(exc).__name__}: {exc}; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT


def _validate_timeout(name: str, timeout_sec: float | None) -> int | None:
    """Validate per-shim timeout metadata without trying to kill in-process code."""
    if timeout_sec is None:
        return None
    if timeout_sec <= 0:
        print(
            f"hook-dispatch: shim {name} has invalid timeout {timeout_sec}; "
            "denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT
    return None


def run_dispatch(
    event_dir: Path,
    shim_names: list[str],
    raw_stdin: bytes,
    shim_timeouts: dict[str, float] | None = None,
    *,
    short_circuit: bool = True,
) -> int:
    """Run each named shim in order, in-process; return the dispatch exit code.

    ``short_circuit`` selects the dispatch mode (ADR-068, #2342):

    - **Gate mode** (``short_circuit=True``, the default; used by ``PreToolUse``).
      Fail-closed (ADR-066). Returns ``ALLOW_EXIT`` (0) only when every shim
      allowed. The first shim that exits non-zero denies the tool: the
      dispatcher returns that code and stops, so later guards do not run. A
      registered shim missing on disk, or an unexpected dispatch error, is a
      denial (``BLOCK_EXIT``, 2), never a silent allow.
    - **Observe mode** (``short_circuit=False``; used by ``PostToolUse``,
      ``SessionStart``, ``SessionEnd``, ``UserPromptSubmit``). Observational
      events never gate the host, so EVERY shim runs even when an earlier one
      signals non-zero. A non-zero shim exit (or a missing shim) is logged to
      stderr and the run continues; the dispatcher always returns ``ALLOW_EXIT``
      (0). This matches the per-shim host behavior these events had before
      consolidation, where the host ran all entries and a single observer's exit
      code did not stop the others.
    """
    event_dir = Path(event_dir)
    saved_stdin = sys.stdin
    try:
        for name in shim_names:
            shim_path = event_dir / name
            if not shim_path.is_file():
                # A registered guard that is not on disk is a packaging error.
                # In gate mode, denying is the only safe response; silently
                # skipping it would drop a security guard (fail-open). In
                # observe mode there is nothing to gate, so log and continue
                # to run the remaining observers.
                print(
                    f"hook-dispatch: registered shim missing on disk: {name}",
                    file=sys.stderr,
                )
                if short_circuit:
                    return BLOCK_EXIT
                continue

            timeout_sec = shim_timeouts.get(name) if shim_timeouts else None
            code = _validate_timeout(name, timeout_sec)
            if code is None:
                code = _run_shim(shim_path, name, raw_stdin)

            if code != ALLOW_EXIT:
                if short_circuit:
                    return code
                # Observe mode: an observer's non-zero exit must not gate the
                # host or stop sibling observers. Log and keep going.
                print(
                    f"hook-dispatch: observer {name} exited {code}; continuing "
                    "(observe mode does not gate)",
                    file=sys.stderr,
                )

        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin
