"""Refuse a launch of the Copilot CLI: the error, the gate flag, and the argument check."""

from __future__ import annotations

import os
from collections.abc import Mapping

from local_smoke_command import program_names

LOCAL_SMOKE_ENV = "AI_AGENTS_LOCAL_CLI_SMOKE"
_COPILOT_NAMES = frozenset({"copilot", "copilot.exe", "copilot.cmd", "copilot.bat"})


class CopilotCallRefusedError(BaseException):
    """Raised when the local smoke tries to start the Copilot CLI.

    A ``BaseException`` on purpose, so a broad ``except Exception`` cannot swallow it.
    pytest still reports it as a test failure.
    """


def guard_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when the local pre-push smoke marked this run."""
    source = os.environ if environ is None else environ
    return source.get(LOCAL_SMOKE_ENV) == "1"


def refuse_copilot(args: object) -> None:
    """Raise when ``args`` would start the Copilot CLI."""
    if any(name in _COPILOT_NAMES for name in program_names(args)):
        raise CopilotCallRefusedError(
            f"The local CLI smoke must not call Copilot (got {args!r}). "
            "Give the test the copilot marker (the requires_copilot decorator in "
            "test_plugin_load_smoke.py and test_cli_hook_e2e.py applies it), so "
            "only the CI leg runs it."
        )
