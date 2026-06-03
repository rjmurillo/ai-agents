"""In-process hook dispatcher for Copilot CLI (ADR-067, addresses #2295).

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
- **Fail-closed (ADR-066).** The first shim that exits non-zero denies the tool;
  the dispatcher returns that code and stops. A registered shim missing on disk,
  or an unexpected exception while running a shim, is a denial (exit 2), never a
  silent allow. A shim's own internal fail-open (its ``main`` returning 0 on its
  own error) is preserved, because the dispatcher only observes the shim's final
  exit code.
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


def run_dispatch(event_dir: Path, shim_names: list[str], raw_stdin: bytes) -> int:
    """Run each named shim in order, in-process; return the dispatch exit code.

    Returns ``ALLOW_EXIT`` (0) only when every shim allowed. Returns the first
    non-zero shim exit code otherwise, or ``BLOCK_EXIT`` (2) on a missing shim or
    an unexpected dispatch error (fail-closed, ADR-066). Short-circuits on the
    first denial: once a guard blocks, the tool is denied and remaining guards
    add no information.
    """
    event_dir = Path(event_dir)
    saved_stdin = sys.stdin
    try:
        for name in shim_names:
            shim_path = event_dir / name
            if not shim_path.is_file():
                # A registered guard that is not on disk is a packaging error.
                # Denying is the only safe response; silently skipping it would
                # drop a security guard (fail-open).
                print(
                    f"hook-dispatch: registered shim missing on disk: {name}",
                    file=sys.stderr,
                )
                return BLOCK_EXIT

            _install_stdin(raw_stdin)
            try:
                runpy.run_path(str(shim_path), run_name="__main__")
                # A shim that returns without calling sys.exit allowed the tool.
                code = ALLOW_EXIT
            except SystemExit as exc:
                code = _exit_code(exc)
            except Exception as exc:  # noqa: BLE001 - fail-closed is mandatory
                print(
                    f"hook-dispatch: shim {name} raised "
                    f"{type(exc).__name__}: {exc}; denying (fail-closed)",
                    file=sys.stderr,
                )
                return BLOCK_EXIT

            if code != ALLOW_EXIT:
                return code

        return ALLOW_EXIT
    finally:
        sys.stdin = saved_stdin
