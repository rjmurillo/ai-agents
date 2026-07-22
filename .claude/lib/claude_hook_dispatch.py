"""In-process hook group runner for Claude Code (extends ADR-068 to Claude).

Claude Code honors per-registration ``matcher`` natively, so unlike the
Copilot dispatcher (``hook_dispatch.py``) this runner never needs an
in-process matcher grammar: the host only invokes it when the group's
matcher already fired. What it removes is the per-hook process spawn: a
group of N hooks registered on the same ``(event, matcher)`` pair becomes
ONE interpreter that runs each hook body in-process via ``runpy``.

Canonical source: ``.claude/lib/hook_dispatch.py`` (ADR-068). This module
reuses its stdin, exit-code, and process-level stdout-capture helpers and
mirrors its gate-mode semantics:

- **gate** (``PreToolUse``): fail-closed. Exit 2 and validated blocking
  documents stop the group. Other nonzero exits are Claude hook errors, so
  later gates still run and can block. A registered shim missing on disk, or
  an unexpected exception, is a denial (exit 2), never a silent allow.
- **gate_all** (``UserPromptSubmit``, ``Stop``, ``SubagentStop``): every
  shim runs; a non-zero exit does not stop siblings, but the run's final
  exit code is the first blocking (2) code seen, else the first non-zero
  code. This matches the host behavior where all hooks run and any
  blocking hook blocks the event.
- **observe** (``PostToolUse``, ``SessionStart``, ``PreCompact``): every
  shim runs; failures are logged to stderr; the run always exits 0.

Stricter/looser/different than canonical (``hook_dispatch.py``):

- stdout is captured per shim and merged into one protocol-valid output.
  Capture includes Python streams, direct writes to file descriptor 1, and
  inherited child-process stdout. The Copilot dispatcher applies its own
  event-specific merger or discard policy. Claude Code parses hook stdout as a
  SINGLE JSON document, so this module must merge (see
  ``_emit_merged_output``). This is the exact hazard that sank the earlier ad
  hoc Claude-side dispatcher (see
  ``.agents/analysis/2026-07-14-hook-batching-determination.md``,
  "Rejected code path").
- gate mode treats only a validated *blocking decision document* on stdout as
  terminal. Malformed, allow-shaped, or unsupported structured output fails
  closed. Generic JSON with no protocol keys becomes context and later guards
  still run.
- Per-shim timeout metadata is carried in the manifest for the generator
  and parity tests but is NOT enforced in-process, same as canonical: the
  host owns the group registration's cumulative timeout.

Merge rules for shim stdout (per run):

1. A shim's whole stdout is terminal only when it matches an event-valid
   blocking shape: ``continue: false``; top-level ``decision: block`` for
   Stop/SubagentStop; or nested PreToolUse ``permissionDecision: deny``.
   Malformed, allow-shaped, and unsupported structured objects fail closed in
   gate modes and are suppressed in observe mode.
2. A shim's stdout that parses as a JSON object whose only payload is
   ``hookSpecificOutput.additionalContext`` contributes that text as a
   context part.
3. Other plain text, non-object JSON, and JSON objects with no protocol keys
   contribute verbatim as context. Malformed object-shaped JSON does not.
4. Context parts are joined with a blank line. For events where the host
   treats plain stdout as context (``UserPromptSubmit``, ``SessionStart``,
   ``Stop``, ``SubagentStop``, ``PreCompact``) the joined text is printed
   as plain text. For ``PreToolUse``/``PostToolUse`` it is wrapped in a
   single ``hookSpecificOutput.additionalContext`` JSON document.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from claude_hook_protocol import _classify_stdout  # noqa: E402
from hook_dispatch import (  # noqa: E402
    ALLOW_EXIT,
    BLOCK_EXIT,
    _exit_code,
    _install_stdin,
    _run_capturing_process_stdout,
)

GATE = "gate"
GATE_ALL = "gate_all"
OBSERVE = "observe"
_MODES = (GATE, GATE_ALL, OBSERVE)
_MODE_BY_EVENT = {
    "PreToolUse": GATE,
    "UserPromptSubmit": GATE_ALL,
    "Stop": GATE_ALL,
    "SubagentStop": GATE_ALL,
    "PostToolUse": OBSERVE,
    "SessionStart": OBSERVE,
    "PreCompact": OBSERVE,
}

# Events whose plain stdout the host injects as context directly; JSON
# wrapping there would surface raw JSON text to the model.
_PLAIN_CONTEXT_EVENTS = frozenset(
    {"UserPromptSubmit", "SessionStart", "Stop", "SubagentStop", "PreCompact"}
)

@dataclass
class _ShimOutcome:
    """One shim's classified result."""

    exit_code: int
    raw_stdout: str
    context: str | None = None
    decision: str | None = None
    recognized: bool = True


@dataclass
class _RunState:
    """Accumulated group state across shims."""

    context_parts: list[str] = field(default_factory=list)
    decision: str | None = None
    first_block: int = ALLOW_EXIT


def validate_group(
    event: object,
    mode: object,
    shims: object,
) -> tuple[str, str, list[str]]:
    """Validate one grouped-dispatch contract and return normalized values."""
    if not isinstance(event, str) or not event:
        raise TypeError("group event must be a non-empty string")
    if not isinstance(mode, str) or mode not in _MODES:
        raise ValueError(f"group mode must be one of {_MODES}, got {mode!r}")
    expected_mode = _MODE_BY_EVENT.get(event)
    if expected_mode is None:
        raise ValueError(f"group event {event!r} has no reviewed dispatch mode")
    if mode != expected_mode:
        raise ValueError(f"group event {event!r} requires mode {expected_mode!r}, got {mode!r}")
    if not isinstance(shims, list):
        raise TypeError("group shims must be a list")
    if not shims:
        raise ValueError("group shims must not be empty")

    validated: list[str] = []
    normalized_paths: set[str] = set()
    for shim in shims:
        if not isinstance(shim, str) or not shim:
            raise TypeError("group shim paths must be non-empty strings")
        posix_path = PurePosixPath(shim)
        windows_path = PureWindowsPath(shim)
        if (
            shim != shim.strip()
            or "\x00" in shim
            or "\\" in shim
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in posix_path.parts
            or posix_path.as_posix() != shim
            or posix_path.suffix != ".py"
        ):
            raise ValueError(f"group shim path must stay under the hooks directory: {shim!r}")
        normalized_path = shim.casefold()
        if normalized_path in normalized_paths:
            raise ValueError(f"group shim path is duplicated: {shim!r}")
        validated.append(shim)
        normalized_paths.add(normalized_path)
    return event, mode, validated


def _is_path_within(candidate: Path, directory: Path) -> bool:
    """Return whether candidate is inside directory on the current platform."""
    normalized_candidate = os.path.normcase(os.fspath(candidate))
    normalized_directory = os.path.normcase(os.fspath(directory))
    try:
        return (
            os.path.commonpath((normalized_candidate, normalized_directory))
            == normalized_directory
        )
    except ValueError:
        return False


def _run_one(shim_path: Path, name: str, raw_stdin: bytes, event: str) -> _ShimOutcome:
    """Run one shim in-process with stdin replay and stdout capture."""
    _install_stdin(raw_stdin)
    # Standalone execution puts the script's own directory at sys.path[0],
    # which shims with sibling companion modules rely on (e.g. a hook importing
    # a sibling companion module placed next to it). runpy
    # does not, so restore that contract for the shim's run.
    shim_dir = str(shim_path.parent)
    saved_sys_path = sys.path
    saved_argv = sys.argv
    sys.path = [shim_dir, *saved_sys_path]
    sys.argv = [str(shim_path)]

    def run_shim() -> int:
        try:
            runpy.run_path(str(shim_path), run_name="__main__")
            return ALLOW_EXIT
        except SystemExit as exc:
            return _exit_code(exc)
        except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory
            print(
                f"claude-hook-dispatch: shim {name} raised "
                f"{type(exc).__name__}: {exc}; treating as blocking failure",
                file=sys.stderr,
            )
            return BLOCK_EXIT

    try:
        code, raw = _run_capturing_process_stdout(
            name,
            run_shim,
            diagnostic_prefix="claude-hook-dispatch",
        )
    finally:
        sys.path = saved_sys_path
        sys.argv = saved_argv

    context, decision, recognized = _classify_stdout(raw, event)
    return _ShimOutcome(
        exit_code=code,
        raw_stdout=raw,
        context=context,
        decision=decision,
        recognized=recognized,
    )


def _emit_merged_output(event: str, state: _RunState) -> None:
    """Print exactly one protocol-valid stdout document for the group."""
    if state.decision is not None:
        print(state.decision)
        return
    if not state.context_parts:
        return
    merged = "\n\n".join(state.context_parts)
    if event in _PLAIN_CONTEXT_EVENTS:
        print(merged)
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": merged,
                }
            }
        )
    )


def run_group(
    hooks_dir: Path,
    event: str,
    mode: str,
    shims: list[str],
    raw_stdin: bytes,
) -> int:
    """Run every shim in ``shims`` in-process; return the group exit code."""
    try:
        event, mode, shims = validate_group(event, mode, shims)
    except (TypeError, ValueError) as exc:
        print(f"claude-hook-dispatch: invalid group contract: {exc}", file=sys.stderr)
        return BLOCK_EXIT
    hooks_dir = Path(hooks_dir)
    try:
        resolved_hooks_dir = Path(os.path.realpath(hooks_dir))
    except (OSError, RuntimeError) as exc:
        print(
            f"claude-hook-dispatch: hooks directory cannot be resolved: {exc}",
            file=sys.stderr,
        )
        return BLOCK_EXIT
    state = _RunState()
    resolved_shims: dict[Path, str] = {}
    saved_stdin = sys.stdin
    try:
        for name in shims:
            try:
                shim_path = Path(os.path.realpath(hooks_dir / name))
                if not _is_path_within(shim_path, resolved_hooks_dir):
                    raise ValueError("resolved path escapes hooks directory")
            except (OSError, RuntimeError, ValueError) as exc:
                print(
                    f"claude-hook-dispatch: registered shim path is unsafe: "
                    f"{name}: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                if mode == GATE:
                    return BLOCK_EXIT
                if mode == GATE_ALL:
                    state.first_block = BLOCK_EXIT
                continue
            previous_name = resolved_shims.get(shim_path)
            if previous_name is not None:
                print(
                    "claude-hook-dispatch: registered shim path resolves to "
                    f"duplicate target: {name} aliases {previous_name}",
                    file=sys.stderr,
                )
                if mode == GATE:
                    return BLOCK_EXIT
                if mode == GATE_ALL:
                    state.first_block = BLOCK_EXIT
                continue
            resolved_shims[shim_path] = name
            if not shim_path.is_file():
                print(
                    f"claude-hook-dispatch: registered shim missing on disk: {name}",
                    file=sys.stderr,
                )
                if mode == GATE:
                    return BLOCK_EXIT
                if mode == GATE_ALL:
                    state.first_block = BLOCK_EXIT
                continue

            outcome = _run_one(shim_path, name, raw_stdin, event)

            if outcome.exit_code != ALLOW_EXIT:
                if mode == GATE and outcome.exit_code == BLOCK_EXIT:
                    # Flush this shim's guidance verbatim; it is the only
                    # stdout the host sees for the group (fail-closed,
                    # first block wins, later shims are skipped).
                    if outcome.raw_stdout.strip():
                        sys.stdout.write(outcome.raw_stdout)
                        sys.stdout.flush()
                    return outcome.exit_code
                print(
                    f"claude-hook-dispatch: shim {name} exited "
                    f"{outcome.exit_code} ({mode} mode runs all shims)",
                    file=sys.stderr,
                )
                if mode in {GATE, GATE_ALL}:
                    if outcome.exit_code == BLOCK_EXIT and state.first_block != BLOCK_EXIT:
                        state.first_block = BLOCK_EXIT
                    elif state.first_block == ALLOW_EXIT:
                        state.first_block = outcome.exit_code
                if mode == GATE_ALL:
                    if outcome.context is not None:
                        state.context_parts.append(outcome.context)
                    if outcome.decision is not None:
                        # The block already propagates via the exit code;
                        # surface the structured reason instead of dropping
                        # it (ADR-082 consequence).
                        print(
                            f"claude-hook-dispatch: blocking shim {name} "
                            f"decision document: {outcome.decision}",
                            file=sys.stderr,
                        )
                continue

            if not outcome.recognized and outcome.decision is not None:
                action = (
                    "suppressing in observe mode"
                    if mode == OBSERVE
                    else "denying in gate mode"
                )
                print(
                    f"claude-hook-dispatch: shim {name} emitted invalid or "
                    f"unsupported structured output; {action}",
                    file=sys.stderr,
                )
                if mode == GATE:
                    return BLOCK_EXIT
                if mode == GATE_ALL:
                    state.first_block = BLOCK_EXIT
                continue

            if not outcome.recognized:
                print(
                    f"claude-hook-dispatch: shim {name} emitted JSON with no "
                    "recognized protocol keys; treating it as context and "
                    "continuing",
                    file=sys.stderr,
                )

            if outcome.decision is not None:
                if mode == OBSERVE:
                    print(
                        f"claude-hook-dispatch: shim {name} emitted a valid "
                        "blocking decision; suppressing decision in observe mode",
                        file=sys.stderr,
                    )
                    continue
                if state.decision is None:
                    state.decision = outcome.decision
                else:
                    print(
                        f"claude-hook-dispatch: shim {name} emitted a second "
                        "decision document; keeping the first, logging this one: "
                        f"{outcome.decision}",
                        file=sys.stderr,
                    )
                if mode == GATE:
                    # A structured deny/ask must reach the host alone and
                    # unmodified; later shims are skipped (fail-closed).
                    break
                continue

            if outcome.context is not None:
                state.context_parts.append(outcome.context)

        _emit_merged_output(event, state)
        if mode == OBSERVE:
            return ALLOW_EXIT
        if state.first_block == BLOCK_EXIT:
            return BLOCK_EXIT
        if state.decision is not None:
            return ALLOW_EXIT
        return state.first_block
    finally:
        sys.stdin = saved_stdin
