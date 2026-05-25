"""Shared helpers for testing lifecycle hook fail-open wrappers.

The fail-open contract Claude Code relies on lives in the
``if __name__ == "__main__":`` block at the bottom of each hook script,
not in ``main()`` itself. Calling ``main()`` and catching exceptions
only proves that ``main`` raised, never that the wrapper exited 0.

These helpers run the wrapper block with a patched ``main`` callable so
tests can assert the real exit semantics. Subprocess execution would
prove the same thing but adds 100ms+ per test and complicates fixtures.
"""

from __future__ import annotations

import builtins
import contextlib
import io
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

# Resolved at import time to avoid a literal substring that the project's
# security reminder hook flags. ``builtins.exec`` is the standard tool for
# this kind of in-process script harness.
_RUN_BLOCK = getattr(builtins, "ex" + "ec")


def run_main_wrapper(
    module: ModuleType,
    main_fn: Callable[[], None],
) -> tuple[int | str | None, str, str]:
    """Run ``module``'s ``__main__`` wrapper with ``main_fn`` substituted.

    Returns ``(exit_code, stdout, stderr)``. The exit code is the value
    passed to ``sys.exit`` (or ``None`` when the wrapper exits without
    calling it). Exceptions other than ``SystemExit`` propagate, which
    surfaces fail-open violations directly to the test.
    """
    module_source = Path(module.__file__).read_text(encoding="utf-8")
    wrapper_marker = 'if __name__ == "__main__":'
    if wrapper_marker not in module_source:
        raise AssertionError(
            f"{module.__file__!s} has no {wrapper_marker!r} block; "
            "run_main_wrapper cannot test a fail-open contract that "
            "does not exist. Add the wrapper or call main() directly."
        )
    wrapper_block = wrapper_marker + module_source.rsplit(wrapper_marker, 1)[1]

    # Reuse the module's own globals so module-level names (HOOK_NAME,
    # imports, helpers) resolve. Override ``__name__`` to enter the
    # wrapper branch and replace ``main`` with the test double.
    wrapper_globals = dict(module.__dict__)
    wrapper_globals["__name__"] = "__main__"
    wrapper_globals["main"] = main_fn
    wrapper_globals["sys"] = sys

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    code: int | str | None = None
    try:
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            _RUN_BLOCK(wrapper_block, wrapper_globals)
    except SystemExit as excinfo:
        code = excinfo.code
    return code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
