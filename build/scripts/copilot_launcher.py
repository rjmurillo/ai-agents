"""The one launcher recipe for a Copilot CLI command that runs a shipped script.

Issue #5521. A shipped command is authored for a POSIX shell:

    (plugin-root-interpreter: docstring example, illustrative only)
    python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/y.py" ARGS

On a Windows Copilot CLI host that line fails twice. PowerShell reads the nested
``${VAR:-default}`` as a braced variable name, so the root is empty, and the host
may expose Python only as ``py -3`` or ``python.exe``, never ``python3``
(REQ-003-multi-tool-artifact-build.md Risks, "Python on Windows runner PATH").

:func:`render_launcher` is the single definition of the form that works in both
shells. It is a ``pwsh -NoProfile -CommandWithArgs '<payload>' ARGS`` command:

* **One command line for both shells.** The payload is single-quoted, so a POSIX
  parent shell passes it to ``pwsh`` untouched (a double-quoted payload would
  have ``$root`` and ``$env:`` expanded away before ``pwsh`` ran), and a
  PowerShell parent reads it as a literal string. ``pwsh`` runs on Linux and
  macOS, so a POSIX Copilot host that has it keeps working.
* **Root and interpreter resolved once.** The root is the first set value of
  ``COPILOT_PLUGIN_ROOT``, ``CLAUDE_PLUGIN_ROOT``, then ``.claude``, which is the
  chain the POSIX form spells. The interpreter is the first of ``python3``,
  ``py -3``, ``python`` that exists. ``python3`` goes first because ``py`` exists
  only on Windows.
* **The script's exit code is the command's exit code.** ``pwsh -Command`` maps
  any non-zero native exit to 1. ``exit $LASTEXITCODE`` restores the real value,
  which the PR workflows branch on (``check_transport`` exits 3 for a quota
  window and 4 for a credential fault).
* **Arguments pass through.** ``-CommandWithArgs`` (PowerShell 7.4 or later)
  exposes the words after the payload as ``$args``, so a quoted multi-word value
  survives. ``-Command`` joins them into the command text and loses the quoting.

The payload holds no ``|``. A launcher quoted inside a Markdown table cell would
otherwise split the row.

Only ``scripts.copilot`` in ``pr-review-config.yaml`` is dispatched verbatim by a
workflow, so only that map is written in this form. A Markdown bash block is a
POSIX program (functions, arrays, pipelines) that no per-call rewrite can turn
into PowerShell; ``pr-autofix`` says so for its Phase 0 block. This module does
not translate those.

``tests/build_scripts/test_copilot_launcher.py`` enforces that every
``scripts.copilot`` entry equals :func:`render_launcher` of its own script, so
the recipe cannot fork into per-entry copies, and runs each entry under ``pwsh``
from a foreign working directory.
"""

from __future__ import annotations

import re

ROOT_ENV_VARS: tuple[str, str] = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")
FALLBACK_ROOT = ".claude"
LAUNCHER_PREFIX = "pwsh -NoProfile -CommandWithArgs "

# A script path under the plugin root. The class excludes quotes, `$`, spaces,
# and backslashes, so the path can sit inside the payload's double quotes with
# no escaping; `..` and a leading `/` are rejected separately.
_SCRIPT_REL_RE = re.compile(r"skills/[A-Za-z0-9_.\-/]+\.py")
_PAYLOAD_RE = re.compile(
    r"'[^']*?\(Join-Path \$root \"(?P<rel>[^\"]+)\"\) @args; exit \$LASTEXITCODE'"
    r"(?: (?P<tail>.*))?$"
)


class LauncherError(ValueError):
    """The script path cannot be placed inside the launcher payload."""


def _root_expression() -> str:
    first, second = ROOT_ENV_VARS
    return (
        f"$root = if ($env:{first}) {{ $env:{first} }} "
        f"elseif ($env:{second}) {{ $env:{second} }} "
        f'else {{ "{FALLBACK_ROOT}" }}'
    )


def _interpreter_expression() -> str:
    return (
        "$exe, $pre = if (Get-Command python3 -EA SilentlyContinue) "
        '{ "python3", @() } '
        "elseif (Get-Command py -EA SilentlyContinue) "
        '{ "py", @("-3") } '
        'else { "python", @() }'
    )


def render_payload(script_rel: str) -> str:
    """Return the PowerShell payload that runs ``script_rel`` under the plugin root."""
    if not _SCRIPT_REL_RE.fullmatch(script_rel) or ".." in script_rel.split("/"):
        raise LauncherError(f"not a plugin-root script path: {script_rel!r}")
    return (
        f"{_root_expression()}; {_interpreter_expression()}; "
        f'& $exe @pre (Join-Path $root "{script_rel}") @args; exit $LASTEXITCODE'
    )


def render_launcher(script_rel: str, args: str = "") -> str:
    """Return the cross-shell command line that runs ``script_rel`` with ``args``.

    ``script_rel`` is relative to the plugin root and starts with ``skills/``.
    ``args`` is appended verbatim after the payload, in whatever dialect the
    caller's shell reads.
    """
    command = f"{LAUNCHER_PREFIX}'{render_payload(script_rel)}'"
    return f"{command} {args}" if args else command


def split_launcher(command: str) -> tuple[str, str] | None:
    """Return ``(script_rel, args)`` when ``command`` is a launcher, else ``None``.

    The inverse of :func:`render_launcher`, used to ask whether an existing
    command is the canonical form of its own script.
    """
    if not command.startswith(LAUNCHER_PREFIX):
        return None
    match = _PAYLOAD_RE.search(command[len(LAUNCHER_PREFIX) :])
    if match is None:
        return None
    return match.group("rel"), match.group("tail") or ""
