"""Hook protocol I/O shared by SessionStart hooks.

NOTE: Plugin-distributed copies are generated from this canonical
``scripts/`` tree. Do not hand-edit the generated copies; edit this
file and regenerate.
"""

from __future__ import annotations

import io
import sys


def drain_stdin() -> None:
    """Drain stdin so the harness pipe never blocks.

    A hook that needs no input still consumes stdin to keep the fail-open
    contract: an unconsumed pipe can leave the producer blocked or trigger
    EPIPE/SIGPIPE when the hook exits.
    """
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def emit_utf8(text: str) -> None:
    """Prefer UTF-8 protocol output, with an ambient-encoding text fallback."""
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (
            AttributeError,
            TypeError,
            ValueError,
            io.UnsupportedOperation,
            OSError,
        ):
            pass
        else:
            stream.write(text + "\n")
            stream.flush()
            return

    payload = bytes(f"{text}\n", encoding="utf-8")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
        buffer.flush()
        return

    stream.write(text + "\n")
    stream.flush()
