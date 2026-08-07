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

from pathlib import Path
from types import CodeType


class ShimLoadError(Exception):
    """The shim could not be read or compiled, so none of it executed.

    A distinct type rather than a sentinel, so a caller cannot mistake "did not
    load" for "ran and returned nothing". The distinction decides whether the
    dispatcher degrades or denies, which is the whole security boundary here.
    """


def load_shim(shim_path: Path) -> CodeType:
    """Compile *shim_path* without executing any of it.

    Raises ``ShimLoadError`` when the file cannot be read or cannot be
    compiled. Every other failure belongs to execution and is the caller's to
    classify.
    """
    try:
        source = shim_path.read_text(encoding="utf-8")
        return compile(source, str(shim_path), "exec")
    except (OSError, SyntaxError, ValueError) as exc:
        raise ShimLoadError(f"{type(exc).__name__}: {exc}") from exc


def execute_shim(code: CodeType, shim_path: Path) -> None:
    """Execute already-compiled shim *code* with ``__main__`` semantics.

    Mirrors what ``runpy.run_path`` provided, minus the compile step, which
    ``load_shim`` performs separately.
    """
    namespace: dict[str, object] = {
        "__name__": "__main__",
        "__file__": str(shim_path),
        "__builtins__": __builtins__,
    }
    exec(code, namespace)
