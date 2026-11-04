"""Loading a plugin shim, kept separate from running it.

The split is the point, not an organizational preference. Catching
``ImportError`` around ``runpy.run_path`` could not tell a shim that failed to
load from one that loaded, read the request, and then raised: ``run_path``
performs both steps. A shim could therefore reach the degraded path
deliberately and turn a policy decision into an allow, which bypasses the gate.

Compiling first separates the two by construction. A compile failure means no
shim code ran, so there is no verdict to honor and degrading is correct. Once
compilation succeeds, execution has begun and every exception is a policy
failure that must fail closed, including ``ImportError``.

Refs #4672.
"""

from __future__ import annotations

import ast
import runpy
from pathlib import Path


class ShimLoadError(Exception):
    """The shim could not be read or compiled, so none of it executed.

    A distinct type rather than a sentinel, so a caller cannot mistake "did not
    load" for "ran and returned nothing". The distinction decides whether the
    dispatcher degrades or denies, which is the whole security boundary here.
    """


def check_shim_loads(shim_path: Path) -> None:
    """Prove *shim_path* can be read and parsed, without producing runnable code.

    ``ast.parse`` answers the only question this step asks, whether the file is
    readable and syntactically valid, and it yields a syntax tree rather than a
    code object, so nothing here can be executed later by accident.

    An earlier version called ``compile()``. That produced a code object and
    tripped a dynamic-code-compilation finding, correctly: a compile step whose
    output is executed later is a materially different thing from a parse whose
    output is discarded. Parsing keeps the load and execute phases separate
    without adding an executable artifact to do it.

    Raises ``ShimLoadError`` when the file cannot be read or cannot be parsed.
    Every other failure belongs to execution and is the caller's to classify.
    """
    try:
        source = shim_path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(shim_path))
    except (OSError, SyntaxError, ValueError) as exc:
        raise ShimLoadError(f"{type(exc).__name__}: {exc}") from exc


def execute_shim(shim_path: Path) -> None:
    """Execute *shim_path* with ``__main__`` semantics.

    Called only after ``check_shim_loads`` succeeded, so a failure here means
    the shim ran and then raised, which is a policy outcome rather than an
    infrastructure one.
    """
    runpy.run_path(str(shim_path), run_name="__main__")
