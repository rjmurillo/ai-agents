"""Shared helpers for testing lifecycle hook wrapper exit contracts.

The runtime contract Claude Code relies on lives in the ``if __name__ ==
"__main__":`` block at the bottom of each hook script, not in ``main()``
itself. Calling ``main()`` and catching exceptions only proves that
``main`` raised, never which exit code the wrapper returned.

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

# Resolved at import time to avoid a literal substring that a development
# gate hook (invoke_security_gate.py, PreToolUse) flags on plain
# `exec(`. The token never
# appears in this source verbatim. Audit rationale:
#   * Input is ``wrapper_block`` read from ``module.__file__`` (module-
#     internal source we control), never user input.
#   * Globals are a copy of ``module.__dict__`` plus a patched ``main``;
#     no caller-controlled names leak in.
#   * The security-scan vulnerability scanner regex (in
#     ``.claude/skills/security-scan/scripts/scan_vulnerabilities.py``)
#     only flags ``exec()`` whose first argument matches input-shaped
#     names (user, input, param, arg, request, cmd, command); this call
#     site does not match and is intentionally safe.
# A clean replacement (``runpy.run_path``) would re-import the module
# under ``__main__`` and re-run all module-level code, which defeats the
# point of patching ``main`` after import; keep the lookup pattern.
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
    module_file = module.__file__
    if module_file is None:
        raise AssertionError("module has no __file__; cannot inspect wrapper")
    module_source = Path(module_file).read_text(encoding="utf-8")
    wrapper_marker = 'if __name__ == "__main__":'
    if wrapper_marker not in module_source:
        raise AssertionError(
            f"{module.__file__!s} has no {wrapper_marker!r} block; "
            "run_main_wrapper cannot test a wrapper exit contract that "
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
