"""The one recipe for the shell locator that runs a shipped plugin script (ADR-121).

A shipped command that a model runs in a shell is authored as the locator below.
It tries each candidate plugin root in order and runs the first root that holds
``lib/ptk_run.py``, passing the script path and its arguments to that resolver:

    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do ...; done; ...; exit 2 )

(abridged; ADR-121 decision 3 prints the whole text.)

The locator keys on the resolver, not on the target. A foreign plugin that
exports its own ``CLAUDE_PLUGIN_ROOT`` holds no ``lib/ptk_run.py``, so the loop
skips it and reaches a root of ours (ADR-121 decisions 3 to 5). The subshell
keeps ``exit 2`` from ending a persistent shell. The text holds no ``|``, so it
survives a Markdown table cell.

:func:`render_locator` is the single definition of the text. :func:`split_locator`
is its inverse. Rollout step 3 teaches the validator to read the target out of an
existing site with :func:`split_locator`.

Authored sites hold the expanded text because skill templates reject ``{{var}}``
and ``references/`` files are byte copies. Class G (gate-dispatched YAML) and
Class P (the Copilot ``pwsh`` form in ``copilot_launcher.py``) do not use this
recipe (ADR-121 decision 1).

Same target pattern as ``copilot_launcher._SCRIPT_REL_RE`` and
``src/claude/lib/ptk_run.TARGET_RE``;
``tests/build_scripts/test_plugin_run_launcher.py`` pins all three.
"""

from __future__ import annotations

import re

RESOLVER_REL = "lib/ptk_run.py"
ROOT_ENV_VARS: tuple[str, str] = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
FALLBACK_ROOT = ".claude"
FAILURE_MESSAGE = f"ptk_run: no plugin root holds {RESOLVER_REL}"

# A script path under the plugin root. `..` parts are rejected separately.
_SCRIPT_REL_RE = re.compile(r"skills/[A-Za-z0-9_./-]+\.py")

_CANDIDATES = " ".join([*(f'"${{{name}}}"' for name in ROOT_ENV_VARS), FALLBACK_ROOT])
_HEAD = (
    f"( for d in {_CANDIDATES}; do "
    f'if [ -n "$d" ] && [ -f "$d/{RESOLVER_REL}" ]; then '
    f'exec python3 "$d/{RESOLVER_REL}" '
)
_TAIL = f'; fi; done; echo "{FAILURE_MESSAGE}" >&2; exit 2 )'


class LauncherError(ValueError):
    """The script path cannot be placed in the locator."""


def _check_script_rel(script_rel: str) -> None:
    if not _SCRIPT_REL_RE.fullmatch(script_rel) or ".." in script_rel.split("/"):
        raise LauncherError(f"not a plugin-root script path: {script_rel!r}")


def render_locator(script_rel: str, args: str = "") -> str:
    """Return the locator that runs ``script_rel`` with ``args``.

    ``script_rel`` is relative to the plugin root and starts with ``skills/``.
    ``args`` is appended verbatim after the script path, in POSIX shell syntax.
    """
    _check_script_rel(script_rel)
    return f"{_HEAD}{script_rel} {args}{_TAIL}" if args else f"{_HEAD}{script_rel}{_TAIL}"


def split_locator(text: str) -> tuple[str, str] | None:
    """Return ``(script_rel, args)`` when ``text`` is a locator, else ``None``.

    The inverse of :func:`render_locator`. Text of another shape returns
    ``None``. A locator whose script path fails the pattern raises
    :class:`LauncherError`, the same as :func:`render_locator`.
    """
    if len(text) < len(_HEAD) + len(_TAIL):
        return None
    if not (text.startswith(_HEAD) and text.endswith(_TAIL)):
        return None
    middle = text[len(_HEAD) : len(text) - len(_TAIL)]
    script_rel, _, args = middle.partition(" ")
    _check_script_rel(script_rel)
    return script_rel, args
