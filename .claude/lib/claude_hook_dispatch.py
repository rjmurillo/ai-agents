"""In-process hook group runner for Claude Code (extends ADR-068 to Claude).

Claude Code honors per-registration ``matcher`` natively, so unlike the
Copilot dispatcher (``hook_dispatch.py``) this runner never needs an
in-process matcher grammar: the host only invokes it when the group's
matcher already fired. What it removes is the per-hook process spawn: a
group of N hooks registered on the same ``(event, matcher)`` pair becomes
ONE interpreter that runs each hook body in-process via ``runpy``.

Canonical source: ``.claude/lib/hook_dispatch.py`` (ADR-068). This module
reuses its ``_install_stdin`` / ``_exit_code`` helpers and mirrors its
gate-mode semantics:

- **gate** (``PreToolUse``): fail-closed. The first shim that exits
  non-zero ends the run with that exit code (its captured stdout is
  flushed verbatim so block guidance reaches the host). A registered shim
  missing on disk, or an unexpected exception, is a denial (exit 2),
  never a silent allow.
- **gate_all** (``UserPromptSubmit``, ``Stop``, ``SubagentStop``): every
  shim runs; a non-zero exit does not stop siblings, but the run's final
  exit code is the first blocking (2) code seen, else the first non-zero
  code. This matches the host behavior where all hooks run and any
  blocking hook blocks the event.
- **observe** (``PostToolUse``, ``SessionStart``, ``PreCompact``): every
  shim runs; failures are logged to stderr; the run always exits 0.

Stricter/looser/different than canonical (``hook_dispatch.py``):

- stdout is CAPTURED per shim and merged into one protocol-valid output
  instead of streamed through. The Copilot dispatcher streams shim stdout
  directly, which can concatenate multiple JSON objects; Claude Code
  parses hook stdout as a SINGLE JSON document, so this module must merge
  (see ``_emit_merged_output``). This is the exact hazard that sank the
  earlier ad hoc Claude-side dispatcher (see
  ``.agents/analysis/2026-07-14-hook-batching-determination.md``,
  "Rejected code path").
- gate mode additionally treats a *structured decision document* on
  stdout (deny/ask JSON emitted with exit 0, e.g. by
  ``invoke_routing_gates.py``) as terminal: it is emitted verbatim and
  later shims are skipped. Streaming it alongside sibling output would
  corrupt the host's JSON parse.
- Per-shim timeout metadata is carried in the manifest for the generator
  and parity tests but is NOT enforced in-process, same as canonical: the
  host owns the group registration's cumulative timeout.

Merge rules for shim stdout (per run):

1. A shim's whole stdout that parses as a JSON object with any decision
   key (``decision``, ``continue``, ``permissionDecision``, or a
   ``hookSpecificOutput`` carrying more than ``additionalContext``) is a
   decision document: emitted verbatim, alone. In gate mode it
   short-circuits; in gate_all/observe the first one wins and later ones
   are logged to stderr (never concatenated).
2. A shim's stdout that parses as a JSON object whose only payload is
   ``hookSpecificOutput.additionalContext`` contributes that text as a
   context part.
3. Any other non-empty stdout contributes verbatim as a context part.
4. Context parts are joined with a blank line. For events where the host
   treats plain stdout as context (``UserPromptSubmit``, ``SessionStart``,
   ``Stop``, ``SubagentStop``, ``PreCompact``) the joined text is printed
   as plain text. For ``PreToolUse``/``PostToolUse`` it is wrapped in a
   single ``hookSpecificOutput.additionalContext`` JSON document.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_dispatch import ALLOW_EXIT, BLOCK_EXIT, _exit_code, _install_stdin  # noqa: E402

GATE = "gate"
GATE_ALL = "gate_all"
OBSERVE = "observe"
_MODES = (GATE, GATE_ALL, OBSERVE)

# Events whose plain stdout the host injects as context directly; JSON
# wrapping there would surface raw JSON text to the model.
_PLAIN_CONTEXT_EVENTS = frozenset(
    {"UserPromptSubmit", "SessionStart", "Stop", "SubagentStop", "PreCompact"}
)

_DECISION_KEYS = frozenset({"decision", "continue", "permissionDecision"})


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


def _classify_stdout(text: str) -> tuple[str | None, str | None, bool]:
    """Return ``(context, decision, recognized)`` for one shim's stdout.

    ``recognized`` is False only for the protocol-transparent fallthrough
    (a JSON object with no known protocol keys); callers warn on stderr so
    an accidental debug document terminating a gate group is observable.
    """
    stripped = text.strip()
    if not stripped:
        return None, None, True
    try:
        doc = json.loads(stripped)
    except ValueError:
        return stripped, None, True
    if not isinstance(doc, dict):
        return stripped, None, True
    if _DECISION_KEYS & doc.keys():
        return None, stripped, True
    hso = doc.get("hookSpecificOutput")
    if isinstance(hso, dict):
        extra_keys = set(hso.keys()) - {"hookEventName", "additionalContext"}
        top_keys = set(doc.keys()) - {"hookSpecificOutput", "suppressOutput", "systemMessage"}
        if extra_keys or top_keys:
            return None, stripped, True
        context = hso.get("additionalContext")
        if isinstance(context, str) and context.strip():
            return context, None, True
        return None, None, True
    # Advisory-only documents (the LSP guards emit standalone
    # {"systemMessage": ...} on their warn path) must never terminate a
    # gate group: surface the message as context and keep running.
    if set(doc.keys()) <= {"systemMessage", "suppressOutput"}:
        message = doc.get("systemMessage")
        if isinstance(message, str) and message.strip():
            return message, None, True
        return None, None, True
    # A JSON object with no recognized protocol keys: pass through as a
    # decision document rather than re-wrapping it (protocol-transparent),
    # flagged unrecognized so the caller logs it.
    return None, stripped, False


def _run_one(shim_path: Path, name: str, raw_stdin: bytes) -> _ShimOutcome:
    """Run one shim in-process with stdin replay and stdout capture."""
    _install_stdin(raw_stdin)
    raw_buffer = io.BytesIO()
    capture = io.TextIOWrapper(raw_buffer, encoding="utf-8", errors="replace")
    saved_stdout = sys.stdout
    sys.stdout = capture
    # Standalone execution puts the script's own directory at sys.path[0],
    # which shims with sibling companion modules rely on (e.g.
    # Stop/invoke_skill_learning.py importing skill_pattern_loader). runpy
    # does not, so restore that contract for the shim's run.
    shim_dir = str(shim_path.parent)
    sys.path.insert(0, shim_dir)
    try:
        runpy.run_path(str(shim_path), run_name="__main__")
        code = ALLOW_EXIT
    except SystemExit as exc:
        code = _exit_code(exc)
    except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory
        sys.stdout = saved_stdout
        print(
            f"claude-hook-dispatch: shim {name} raised "
            f"{type(exc).__name__}: {exc}; treating as blocking failure",
            file=sys.stderr,
        )
        return _ShimOutcome(exit_code=BLOCK_EXIT, raw_stdout="")
    finally:
        sys.stdout = saved_stdout
        if sys.path and sys.path[0] == shim_dir:
            sys.path.pop(0)
        else:
            try:
                sys.path.remove(shim_dir)
            except ValueError:
                pass
    capture.flush()
    raw = raw_buffer.getvalue().decode("utf-8", errors="replace")
    context, decision, recognized = _classify_stdout(raw)
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
    if mode not in _MODES:
        print(f"claude-hook-dispatch: unknown mode {mode!r}", file=sys.stderr)
        return BLOCK_EXIT
    hooks_dir = Path(hooks_dir)
    state = _RunState()
    saved_stdin = sys.stdin
    try:
        for name in shims:
            shim_path = hooks_dir / name
            if not shim_path.is_file():
                print(
                    f"claude-hook-dispatch: registered shim missing on disk: {name}",
                    file=sys.stderr,
                )
                if mode == GATE:
                    return BLOCK_EXIT
                if mode == GATE_ALL and state.first_block == ALLOW_EXIT:
                    state.first_block = BLOCK_EXIT
                continue

            outcome = _run_one(shim_path, name, raw_stdin)

            if outcome.exit_code != ALLOW_EXIT:
                if mode == GATE:
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
                if mode == GATE_ALL:
                    if outcome.exit_code == BLOCK_EXIT and state.first_block != BLOCK_EXIT:
                        state.first_block = BLOCK_EXIT
                    elif state.first_block == ALLOW_EXIT:
                        state.first_block = outcome.exit_code
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

            if outcome.decision is not None:
                if not outcome.recognized:
                    print(
                        f"claude-hook-dispatch: shim {name} emitted JSON with "
                        "no recognized protocol keys; passing through as a "
                        "decision document",
                        file=sys.stderr,
                    )
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
        if mode == GATE_ALL:
            return state.first_block
        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin
