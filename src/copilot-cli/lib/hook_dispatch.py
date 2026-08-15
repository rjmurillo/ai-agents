"""In-process hook dispatcher for Copilot CLI (ADR-068, addresses #2295).

ADR-068 records a historical Copilot CLI 1.0.57 incident with one process per
registered matcher shim. The aggregate Python interpreter cold-start (~200 ms
each, ~40 shims) caused host kills that denied benign tools (false
fail-closed).

This dispatcher collapses N per-shim host registrations into one. The host
spawns a single interpreter per event; an untimed shim runs *in process* via
``runpy``, while a shim carrying timeout metadata runs in a child process so
its bound is enforceable (#4706). Cold-start savings apply only to untimed
shims.

Design contract (the security-critical part):

- **Manifest-driven, not directory-driven.** The shim list is supplied by the
  caller from the generator's registered-entry list (the same source as
  ``hooks.json``). Orphaned ``invoke_*.py`` files on disk are never executed.
- **Gate vs observe mode (ADR-068, #2342).** ``run_dispatch`` takes a
  ``short_circuit`` flag. In gate mode (``PreToolUse``) the first shim that exits
  non-zero denies the tool (fail-closed, ADR-066). A shim that cannot load
  (SyntaxError, ImportError) degrades with exit 0 (#4672); a shim that loads
  and raises during execution denies (exit 2). Per-shim timeout metadata is
  enforced for gate shims since #4706 (a timed shim runs in a child process
  and a timeout denies); observe mode ignores it and the host owns the
  cumulative event timeout. In
  observe mode every shim runs regardless; failures are logged and the
  dispatcher returns 0. Current generated observers are ``PostToolUse``,
  ``PreCompact``, ``SessionStart``, and ``UserPromptSubmit``.
- **stdin replay.** Each shim reads ``sys.stdin.buffer``; the dispatcher rewinds
  a fresh stream of the original bytes before each shim, so every shim inspects
  exactly the payload the host delivered (no #2290 schema mutation).
- **Observer output translation.** Copilot parses at most one final JSON
  document per command hook. PostToolUse shim stdout is merged into one
  ``additionalContext`` response. SessionStart, PreCompact, and UserPromptSubmit
  stdout is captured and discarded (current producers include repository prose
  that must not reach model-visible channels). Only successful observers
  contribute; partial stdout from a failing observer is discarded.
- **Host-timeout residual.** ADR-068 records: "A `timeoutSec: 2` probe timed
  out and failed open, then executed the tool." A timeout can therefore allow
  a tool before later guards run.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import output_capture  # noqa: E402
from hook_dispatch_protocol import (  # noqa: E402
    OUTPUT_POLICIES as _OUTPUT_POLICIES,
)
from hook_dispatch_protocol import (  # noqa: E402
    copilot_permission_response as _copilot_permission_response,
)
from hook_dispatch_protocol import (  # noqa: E402
    emit_observer_output as _emit_observer_output,
)
from hook_dispatch_protocol import (  # noqa: E402
    observe_output_policy,  # noqa: F401
)
from hook_dispatch_protocol import (  # noqa: E402
    record_discarded_observer_output as _record_discarded_observer_output,
)
from hook_dispatch_timeout import run_timed_shim as _run_timed_shim  # noqa: E402
from shim_loader import ShimLoadError, check_shim_loads, execute_shim  # noqa: E402

# Hook exit-code convention (Claude/Copilot PreToolUse): 0 allow, 2 block.
ALLOW_EXIT = 0
BLOCK_EXIT = 2


def _install_stdin(raw: bytes) -> None:
    """Point ``sys.stdin`` at a fresh stream over ``raw``.

    TextIOWrapper over BufferedReader exposes both ``.buffer`` (read by the
    matcher-shim layer) and ``.read()`` (read by a wrapped original hook).
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


def _run_shim(
    shim_path: Path,
    name: str,
    raw_stdin: bytes,
    timeout_sec: float | None = None,
) -> int:
    """Run one shim and translate its outcome to a hook exit code.

    Load and execute are separate calls so a load failure and an execution
    failure are distinguished by construction, not by exception type. See
    shim_loader for why that boundary is load bearing.

    A shim carrying timeout metadata runs in a child process instead. The
    timeout was validated but never applied, so a hung shim blocked the hook
    indefinitely while the manifest advertised a bound (#4706). An in-process
    thread cannot be killed safely, so enforcing the bound requires a process
    the dispatcher can terminate. Untimed shims keep the in-process path, which
    is the startup win ADR-068 exists for.
    """
    try:
        check_shim_loads(shim_path)
    except ShimLoadError as exc:
        print(
            f"project-toolkit@ai-agents WARNING: hooks DISABLED (your session "
            f"is unaffected). Shim {name} could not be loaded ({exc}); "
            f"infrastructure failure, not a policy denial. Reinstall: "
            f"copilot plugin install project-toolkit@ai-agents",
            file=sys.stderr,
        )
        return ALLOW_EXIT

    if timeout_sec is not None:
        code, _, _ = _run_timed_shim(shim_path, name, raw_stdin, timeout_sec)
        return code

    _install_stdin(raw_stdin)

    try:
        execute_shim(shim_path)
        # A shim that returns without calling sys.exit allowed the tool.
        return ALLOW_EXIT
    except SystemExit as exc:
        # Only an explicit sys.exit() is a policy verdict.
        return _exit_code(exc)
    except Exception as exc:
        # Execution failure: affects one call, no uninstall pressure. Deny.
        print(
            f"hook-dispatch: shim {name} raised {type(exc).__name__}: "
            f"{exc}; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT


def _run_shim_capturing_stdout(
    shim_path: Path,
    name: str,
    raw_stdin: bytes,
    timeout_sec: float | None = None,
) -> tuple[int, str]:
    """Run one shim while retaining every process stdout path."""
    return output_capture.run_capturing_process_stdout(
        name,
        lambda: _run_shim(shim_path, name, raw_stdin, timeout_sec),
        failure_exit=BLOCK_EXIT,
    )


def _run_shim_capturing_output(
    shim_path: Path,
    name: str,
    raw_stdin: bytes,
    timeout_sec: float | None = None,
) -> tuple[int, str, str]:
    """Run one shim while retaining every process stdout and stderr path."""
    return output_capture.run_capturing_process_output(
        name,
        lambda: _run_shim(shim_path, name, raw_stdin, timeout_sec),
        capture_stderr=True,
        failure_exit=BLOCK_EXIT,
    )


def run_permission_dispatch(
    event_dir: Path,
    shim_names: list[str],
    raw_stdin: bytes,
    shim_timeouts: dict[str, float] | None = None,
) -> int:
    """Run and translate exactly one Copilot PermissionRequest producer.

    Exit 2 and every other non-zero exit propagate unchanged. The adapter never
    turns a host failure into exit 0 or rewrites it as exit 2. On exit 0, only a
    recognized canonical decision produces stdout.
    """
    if len(shim_names) != 1:
        print(
            "hook-dispatch: PermissionRequest requires exactly one decision producer",
            file=sys.stderr,
        )
        return BLOCK_EXIT
    event_dir = Path(event_dir)
    name = shim_names[0]
    shim_path = event_dir / name
    if not shim_path.is_file():
        print(
            f"hook-dispatch: registered shim missing on disk: {name}",
            file=sys.stderr,
        )
        return BLOCK_EXIT

    saved_stdin = sys.stdin
    try:
        timeout_sec = shim_timeouts.get(name) if shim_timeouts else None
        code = _validate_timeout(name, timeout_sec)
        if code is not None:
            return code
        code, raw_stdout = _run_shim_capturing_stdout(
            shim_path, name, raw_stdin, timeout_sec
        )
        if code != ALLOW_EXIT:
            return code
        response = _copilot_permission_response(raw_stdout, name)
        if response is not None:
            print(json.dumps(response))
        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin


def _validate_timeout(name: str, timeout_sec: float | None) -> int | None:
    """Validate per-shim timeout metadata without trying to kill in-process code."""
    if timeout_sec is None:
        return None
    if timeout_sec <= 0:
        print(
            f"hook-dispatch: shim {name} has invalid timeout {timeout_sec}; denying (fail-closed)",
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
    output_policy: str = "passthrough",
) -> int:
    """Run each named shim in order, in-process; return the dispatch exit code.

    ``short_circuit`` selects the dispatch mode (ADR-068, #2342):

    - **Gate mode** (``short_circuit=True``, the default; used by ``PreToolUse``).
      Fail-closed (ADR-066). Returns ``ALLOW_EXIT`` (0) only when every shim
      allowed. The first shim that exits non-zero denies the tool: the
      dispatcher returns that code and stops, so later guards do not run. A
      registered shim missing on disk, or an unexpected dispatch error, is a
      denial (``BLOCK_EXIT``, 2), never a silent allow.
    - **Observe mode** (``short_circuit=False``). Current generated users are
      ``PostToolUse``, ``PreCompact``, ``SessionStart``, and
      ``UserPromptSubmit``. ``SessionEnd`` would use this mode if configured.
      Observational events never gate the host, so EVERY shim runs even when an
      earlier one signals non-zero. A non-zero shim exit (or a missing shim) is
      logged to stderr and the run continues; the dispatcher always returns
      ``ALLOW_EXIT`` (0). This matches the per-shim host behavior these events
      had before consolidation, where the host ran all entries and a single
      observer's exit code did not stop the others.

    ``output_policy`` controls observer stdout. ``additional_context`` merges
    nonblank output in shim order into one Copilot response. Capture covers
    Python streams, direct file-descriptor writes, and inherited child-process
    output. ``discard`` captures both stdout and stderr before dropping
    branch-controlled repository prose. ``stderr`` keeps unsupported observer
    text out of the host JSON channel. ``passthrough`` preserves gate behavior
    and remains the default for direct callers.
    """
    if output_policy not in _OUTPUT_POLICIES:
        raise ValueError(f"unsupported dispatcher output policy: {output_policy}")
    if short_circuit and not shim_names:
        print(
            "hook-dispatch: gate manifest has no shims; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT
    event_dir = Path(event_dir)
    saved_stdin = sys.stdin
    observer_outputs: list[tuple[str, str]] = []
    capture_observer_output = not short_circuit and output_policy != "passthrough"
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
            if not short_circuit:
                # Observe mode ignores per-shim timeouts on purpose. Enforcing
                # them once made the dispatcher return success while a slow
                # observer was still running, leaving work orphaned behind a
                # hook that had already reported done, which
                # test_timeout_metadata_does_not_background_observer_work pins.
                # The host owns the event timeout, and an observer cannot block
                # a tool call, so there is nothing here worth that risk. Gate
                # mode is different: a hung shim there blocks the call, which
                # is the hazard #4706 describes.
                timeout_sec = None
            raw_stdout = ""
            raw_stderr = ""
            code = _validate_timeout(name, timeout_sec)
            if code is None:
                if capture_observer_output:
                    if output_policy == "discard":
                        code, raw_stdout, raw_stderr = _run_shim_capturing_output(
                            shim_path,
                            name,
                            raw_stdin,
                            timeout_sec,
                        )
                    else:
                        code, raw_stdout = _run_shim_capturing_stdout(
                            shim_path,
                            name,
                            raw_stdin,
                            timeout_sec,
                        )
                        raw_stderr = ""
                else:
                    code = _run_shim(shim_path, name, raw_stdin, timeout_sec)

            discarded_output = False
            if capture_observer_output and output_policy == "discard":
                discarded_output = _record_discarded_observer_output(
                    name,
                    raw_stdout,
                    raw_stderr,
                    event_dir.name,
                    code,
                )
                if discarded_output:
                    observer_outputs.append((name, ""))

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
                continue

            if capture_observer_output:
                if output_policy != "discard" and raw_stdout.strip():
                    observer_outputs.append((name, raw_stdout.rstrip("\r\n")))

        _emit_observer_output(observer_outputs, output_policy, event_dir.name)
        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin
