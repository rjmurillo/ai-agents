"""In-process hook dispatcher for Copilot CLI (ADR-068, addresses #2295).

ADR-068 records a historical Copilot CLI 1.0.57 incident with one process per
registered matcher shim. The aggregate Python interpreter cold-start (~200 ms
each, ~40 shims) caused host kills that denied benign tools (false
fail-closed).

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
  mode every shim runs regardless of an earlier non-zero exit; failures are
  logged and the dispatcher returns 0, matching the old host behavior where
  the host ran all observer entries before consolidation. Current generated
  observers are ``PostToolUse``, ``PreCompact``, ``SessionStart``, and
  ``UserPromptSubmit``. Unclassified events, including ``SessionEnd``, remain
  direct until their output and failure contracts are reviewed.
- **stdin replay.** Each shim reads ``sys.stdin.buffer``; the dispatcher rewinds
  a fresh stream of the original bytes before each shim, so every shim inspects
  exactly the payload the host delivered (no #2290 schema mutation).
- **Observer output translation.** Copilot parses at most one final JSON
  document per command hook. PostToolUse shim stdout is merged in registration
  order into one documented ``additionalContext`` response. SessionStart and
  PreCompact stdout is captured at the Python stream, file-descriptor, and
  inherited child-process levels, then discarded because current producers
  include branch-controlled repository prose that must not reach model-visible
  channels. UserPromptSubmit redirects successful stdout to stderr. Only
  successful observers contribute; partial stdout from a failing observer is
  discarded.
- **Host-timeout residual.**
  ``.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`` records:
  "A `timeoutSec: 2` probe timed out and failed open, then executed the tool."
  A timeout can therefore allow a tool before later guards run.
"""

from __future__ import annotations

import io
import json
import os
import runpy
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, TextIO

# Hook exit-code convention (Claude/Copilot PreToolUse): 0 allow, 2 block.
ALLOW_EXIT = 0
BLOCK_EXIT = 2

# Canonical Claude PermissionRequest decision -> Copilot behavior mapping.
# Copilot accepts only allow or deny. Claude's ask means "make no hook
# decision", so the adapter emits no stdout and lets normal permission
# handling continue. A 1.0.72-1 noninteractive probe denied in that mode; empty
# output is not itself a universal deny contract.
_BEHAVIOR_BY_DECISION = {
    "approve": "allow",
    "deny": "deny",
}
_ADDITIONAL_CONTEXT_EVENTS = frozenset(
    {
        "Notification",
        "PostToolUse",
        "SubagentStart",
        "notification",
        "postToolUse",
        "subagentStart",
    }
)
_DISCARD_OUTPUT_EVENTS = frozenset({"PreCompact", "SessionStart", "preCompact", "sessionStart"})
_OUTPUT_POLICIES = frozenset({"additional_context", "discard", "passthrough", "stderr"})


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
            f"hook-dispatch: shim {name} raised {type(exc).__name__}: {exc}; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT


def _open_capture_stream(fd: int) -> TextIO:
    """Return a UTF-8 text stream over a duplicate of ``fd``."""
    duplicate = os.dup(fd)
    try:
        return os.fdopen(
            duplicate,
            "w",
            buffering=1,
            encoding="utf-8",
            errors="replace",
            newline="",
        )
    except (OSError, ValueError):
        os.close(duplicate)
        raise


def _save_output_fds(capture_stderr: bool) -> tuple[int, int | None]:
    """Flush host streams and duplicate output descriptors for restoration."""
    sys.stdout.flush()
    if capture_stderr:
        sys.stderr.flush()
    saved_stdout_fd = os.dup(1)
    try:
        saved_stderr_fd = os.dup(2) if capture_stderr else None
    except OSError:
        os.close(saved_stdout_fd)
        raise
    return saved_stdout_fd, saved_stderr_fd


def _restore_output_fds(saved_stdout_fd: int, saved_stderr_fd: int | None) -> None:
    """Restore and close saved output descriptors."""
    stdout_error: OSError | None = None
    try:
        os.dup2(saved_stdout_fd, 1)
    except OSError as exc:
        stdout_error = exc
    finally:
        os.close(saved_stdout_fd)

    if saved_stderr_fd is not None:
        try:
            os.dup2(saved_stderr_fd, 2)
        finally:
            os.close(saved_stderr_fd)
    if stdout_error is not None:
        raise stdout_error


def _read_capture(captured_file: BinaryIO) -> str:
    """Read one binary temporary capture file as replacement-safe UTF-8."""
    captured_file.flush()
    captured_file.seek(0)
    return captured_file.read().decode("utf-8", errors="replace")


def _capture_process_output(
    name: str,
    runner: Callable[[], int],
    *,
    capture_stderr: bool,
    diagnostic_prefix: str = "hook-dispatch",
) -> tuple[int, str, str, str | None]:
    """Redirect selected process channels, run the callback, and read output."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with (
        tempfile.TemporaryFile() as captured_stdout_file,
        tempfile.TemporaryFile() as captured_stderr_file,
    ):
        captured_stdout_stream = None
        captured_stderr_stream = None
        capture_error: str | None = None
        try:
            os.dup2(captured_stdout_file.fileno(), 1)
            captured_stdout_stream = _open_capture_stream(1)
            if capture_stderr:
                os.dup2(captured_stderr_file.fileno(), 2)
                captured_stderr_stream = _open_capture_stream(2)
        except (OSError, ValueError) as exc:
            capture_error = (
                f"{diagnostic_prefix}: process output capture setup failed "
                f"for {name}: {exc}; observer not run"
            )
            code = BLOCK_EXIT
        else:
            sys.stdout = captured_stdout_stream
            if captured_stderr_stream is not None:
                sys.stderr = captured_stderr_stream
            try:
                code = runner()
                captured_stdout_stream.flush()
                if captured_stderr_stream is not None:
                    captured_stderr_stream.flush()
            except (OSError, ValueError) as exc:
                capture_error = (
                    f"{diagnostic_prefix}: process output capture failed for {name}: {exc}"
                )
                code = BLOCK_EXIT
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            if captured_stdout_stream is not None:
                captured_stdout_stream.close()
            if captured_stderr_stream is not None:
                captured_stderr_stream.close()

        raw_stdout = _read_capture(captured_stdout_file)
        raw_stderr = _read_capture(captured_stderr_file) if capture_stderr else ""
        return code, raw_stdout, raw_stderr, capture_error


def _run_capturing_process_output(
    name: str,
    runner: Callable[[], int],
    *,
    capture_stderr: bool = False,
    diagnostic_prefix: str = "hook-dispatch",
) -> tuple[int, str, str]:
    """Run a callback while retaining selected process output channels."""
    original_stderr = sys.stderr
    try:
        saved_stdout_fd, saved_stderr_fd = _save_output_fds(capture_stderr)
    except (OSError, ValueError) as exc:
        print(
            f"{diagnostic_prefix}: process output capture unavailable for "
            f"{name}: {exc}; observer not run",
            file=original_stderr,
        )
        return BLOCK_EXIT, "", ""

    try:
        try:
            code, raw_stdout, raw_stderr, capture_error = _capture_process_output(
                name,
                runner,
                capture_stderr=capture_stderr,
                diagnostic_prefix=diagnostic_prefix,
            )
        except (OSError, ValueError) as exc:
            code, raw_stdout, raw_stderr = BLOCK_EXIT, "", ""
            capture_error = (
                f"{diagnostic_prefix}: process output capture setup failed "
                f"for {name}: {exc}; observer not run"
            )
    finally:
        _restore_output_fds(saved_stdout_fd, saved_stderr_fd)

    if capture_error is not None:
        print(capture_error, file=original_stderr)
    return code, raw_stdout, raw_stderr


def _run_capturing_process_stdout(
    name: str,
    runner: Callable[[], int],
    *,
    diagnostic_prefix: str = "hook-dispatch",
) -> tuple[int, str]:
    """Run a callback while retaining Python, file-descriptor, and child stdout."""
    code, raw_stdout, _ = _run_capturing_process_output(
        name,
        runner,
        diagnostic_prefix=diagnostic_prefix,
    )
    return code, raw_stdout


def _run_shim_capturing_stdout(shim_path: Path, name: str, raw_stdin: bytes) -> tuple[int, str]:
    """Run one shim while retaining every process stdout path."""
    return _run_capturing_process_stdout(
        name,
        lambda: _run_shim(shim_path, name, raw_stdin),
    )


def _run_shim_capturing_output(
    shim_path: Path,
    name: str,
    raw_stdin: bytes,
) -> tuple[int, str, str]:
    """Run one shim while retaining every process stdout and stderr path."""
    return _run_capturing_process_output(
        name,
        lambda: _run_shim(shim_path, name, raw_stdin),
        capture_stderr=True,
    )


def observe_output_policy(event: str) -> str:
    """Return the documented Copilot output policy for an observe event."""
    if event in _ADDITIONAL_CONTEXT_EVENTS:
        return "additional_context"
    if event in _DISCARD_OUTPUT_EVENTS:
        return "discard"
    return "stderr"


def _record_discarded_observer_output(
    name: str,
    raw_stdout: str,
    raw_stderr: str,
    event: str,
) -> bool:
    """Report suppressed stderr without exposing its untrusted content."""
    has_stdout = bool(raw_stdout.strip())
    has_stderr = bool(raw_stderr.strip())
    if has_stderr:
        payload = {
            "guard": "hook-dispatch",
            "code": "E_OBSERVER_STDERR",
            "outcome": "stderr_discarded",
            "reason": "observer_emitted_stderr",
            "event": event,
            "shim": name,
            "exit_code": ALLOW_EXIT,
        }
        print(
            f"EVENT={json.dumps(payload, separators=(',', ':'))}",
            file=sys.stderr,
        )
    return has_stdout or has_stderr


def _emit_observer_output(
    outputs: list[tuple[str, str]],
    output_policy: str,
    event: str,
) -> None:
    if output_policy == "additional_context":
        if outputs:
            context = "\n\n".join(text for _, text in outputs)
            print(json.dumps({"additionalContext": context}))
        return

    if output_policy == "discard":
        for name, _ in outputs:
            print(
                f"hook-dispatch: {name} stdout discarded; stderr discarded; "
                f"{event} hook output is not trusted model context",
                file=sys.stderr,
            )
        return

    if output_policy == "stderr":
        for name, text in outputs:
            print(
                f"hook-dispatch: {name} stdout redirected; "
                "no documented Copilot context output field",
                file=sys.stderr,
            )
            print(text, file=sys.stderr)


def _copilot_permission_response(raw_stdout: str, name: str) -> dict[str, object] | None:
    """Translate one canonical Claude permission decision to Copilot fields.

    A canonical decision producer emits this contract:

        {
            "decision": "approve",
            "reason": "Repository policy approved this request.",
        }

    Copilot's host contract uses ``behavior``, ``message``, and ``interrupt``.
    This adapter translates ``approve`` and ``deny``. Canonical ``ask`` has no
    valid Copilot ``behavior`` value, so it emits nothing and preserves the
    host's normal permission flow. A 1.0.72-1 noninteractive probe denied after
    empty output, but that result is mode-dependent host behavior.

    Different than canonical: only the generated Copilot dispatcher calls this
    adapter. Claude Code receives the canonical object unchanged. Blank stdout
    remains blank. Malformed or unrecognized exit-0 output is diagnosed on
    stderr and suppressed so Copilot applies its documented default behavior.
    """
    if not raw_stdout.strip():
        return None
    decision_text = raw_stdout.strip()
    try:
        decision, end = json.JSONDecoder().raw_decode(decision_text)
    except json.JSONDecodeError as exc:
        print(
            f"hook-dispatch: permission shim {name} emitted malformed JSON: {exc}",
            file=sys.stderr,
        )
        return None
    if decision_text[end:].strip():
        print(
            f"hook-dispatch: permission shim {name} emitted trailing content; "
            "advise mode accepts exactly one decision",
            file=sys.stderr,
        )
        return None
    if not isinstance(decision, dict):
        print(
            f"hook-dispatch: permission shim {name} emitted a non-object decision",
            file=sys.stderr,
        )
        return None
    decision_value = decision.get("decision")
    if decision_value == "ask":
        return None
    behavior = None
    if isinstance(decision_value, str):
        behavior = _BEHAVIOR_BY_DECISION.get(decision_value)
    reason = decision.get("reason")
    if behavior is None:
        print(
            f"hook-dispatch: permission shim {name} emitted an unrecognized decision",
            file=sys.stderr,
        )
        return None
    if not isinstance(reason, str):
        print(
            f"hook-dispatch: permission shim {name} decision "
            f"{decision_value!r} requires a string reason",
            file=sys.stderr,
        )
        return None
    return {
        "behavior": behavior,
        "message": reason,
        "interrupt": False,
    }


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
        code, raw_stdout = _run_shim_capturing_stdout(shim_path, name, raw_stdin)
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
            code = _validate_timeout(name, timeout_sec)
            if code is None:
                if capture_observer_output:
                    if output_policy == "discard":
                        code, raw_stdout, raw_stderr = _run_shim_capturing_output(
                            shim_path,
                            name,
                            raw_stdin,
                        )
                    else:
                        code, raw_stdout = _run_shim_capturing_stdout(
                            shim_path,
                            name,
                            raw_stdin,
                        )
                        raw_stderr = ""
                else:
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
                continue

            if capture_observer_output:
                if output_policy == "discard":
                    if _record_discarded_observer_output(
                        name,
                        raw_stdout,
                        raw_stderr,
                        event_dir.name,
                    ):
                        observer_outputs.append((name, ""))
                elif raw_stdout.strip():
                    observer_outputs.append((name, raw_stdout.rstrip("\r\n")))

        _emit_observer_output(observer_outputs, output_policy, event_dir.name)
        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin
