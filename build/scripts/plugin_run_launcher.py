"""The one recipe for the shell locator that runs a shipped plugin script (ADR-121).

A shipped command that a model runs in a shell is authored as the locator below.
It tries each candidate plugin root in order and runs the first root that holds
``lib/ptk_run.py``, passing the script path and its arguments to that resolver:

    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do ...; done; ...; exit 2 )

(abridged; ADR-121 decision 3 prints the whole text.)

The locator keys on the resolver, not on the target. A foreign plugin that
exports its own plugin-root variable holds no ``lib/ptk_run.py``, so the loop
skips it and reaches a root of ours (ADR-121 decisions 3 to 5). The subshell
keeps ``exit 2`` from ending a persistent shell. The text holds no ``|``, so it
survives a Markdown table cell.

:func:`render_locator` is the single definition of the text. :func:`split_locator`
is its inverse. :func:`find_locators` finds every locator in one line of a file,
which is how the validator reads the target out of a site (ADR-121 rollout step 3).

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
from collections.abc import Iterator
from dataclasses import dataclass

RESOLVER_REL = "lib/ptk_run.py"
ROOT_ENV_VARS: tuple[str, str] = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
FALLBACK_ROOT = ".claude"
FAILURE_MESSAGE = f"ptk_run: no plugin root holds {RESOLVER_REL}"

# A script path under the plugin root. `..` parts are rejected separately.
_SCRIPT_REL_RE = re.compile(r"skills/[A-Za-z0-9_./-]+\.py")

# ADR-121 decision 12: the closed set of interpreters the locator may carry.
# The `uv` form is for a skill whose template sets `distribution: repo-local`;
# the validator enforces that, because a consumer install has no `uv`.
DEFAULT_INTERPRETER = "python3"
ISOLATED_INTERPRETER = "python3 -I"
UV_INTERPRETER = "uv run --frozen python"
INTERPRETERS: tuple[str, ...] = (DEFAULT_INTERPRETER, ISOLATED_INTERPRETER, UV_INTERPRETER)

_CANDIDATES = " ".join([*(f'"${{{name}}}"' for name in ROOT_ENV_VARS), FALLBACK_ROOT])
_PREFIX = f'( for d in {_CANDIDATES}; do if [ -n "$d" ] && [ -f "$d/{RESOLVER_REL}" ]; then exec '
_RESOLVER_ARG = f' "$d/{RESOLVER_REL}" '
_HEADS: dict[str, str] = {interp: f"{_PREFIX}{interp}{_RESOLVER_ARG}" for interp in INTERPRETERS}
_HEAD = _HEADS[DEFAULT_INTERPRETER]
_TAIL = f'; fi; done; echo "{FAILURE_MESSAGE}" >&2; exit 2 )'


class LauncherError(ValueError):
    """The script path cannot be placed in the locator."""


def _check_script_rel(script_rel: str) -> None:
    if not _SCRIPT_REL_RE.fullmatch(script_rel) or ".." in script_rel.split("/"):
        raise LauncherError(f"not a plugin-root script path: {script_rel!r}")


def render_locator(script_rel: str, args: str = "", interpreter: str = DEFAULT_INTERPRETER) -> str:
    """Return the locator that runs ``script_rel`` with ``args``.

    ``script_rel`` is relative to the plugin root and starts with ``skills/``.
    ``args`` is appended verbatim after the script path, in POSIX shell syntax.
    ``interpreter`` is one of :data:`INTERPRETERS` (ADR-121 decision 12).
    """
    _check_script_rel(script_rel)
    head = _head_for(interpreter)
    return f"{head}{script_rel} {args}{_TAIL}" if args else f"{head}{script_rel}{_TAIL}"


def _head_for(interpreter: str) -> str:
    try:
        return _HEADS[interpreter]
    except KeyError:
        raise LauncherError(f"interpreter is not one of {INTERPRETERS}: {interpreter!r}") from None


def _head_at(text: str, pos: int) -> tuple[str, str] | None:
    """Return ``(interpreter, head)`` when a locator head starts at ``pos``."""
    for interpreter, head in _HEADS.items():
        if text.startswith(head, pos):
            return interpreter, head
    return None


def split_locator(text: str) -> tuple[str, str] | None:
    """Return ``(script_rel, args)`` when ``text`` is a locator, else ``None``.

    The inverse of :func:`render_locator` for every interpreter. Text of another
    shape returns ``None``. A locator whose script path fails the pattern raises
    :class:`LauncherError`, the same as :func:`render_locator`.
    """
    found = _head_at(text, 0)
    if found is None or not text.endswith(_TAIL):
        return None
    head = found[1]
    if len(text) < len(head) + len(_TAIL):
        return None
    return _split_middle(text[len(head) : len(text) - len(_TAIL)])


def _split_middle(middle: str) -> tuple[str, str]:
    """Return ``(script_rel, args)`` from the text between the head and the tail."""
    script_rel, _, args = middle.partition(" ")
    _check_script_rel(script_rel)
    return script_rel, args


@dataclass(frozen=True, slots=True)
class LocatorMatch:
    """One locator found in a line: its span, and its target or why it has none."""

    start: int
    end: int
    script_rel: str | None
    args: str
    problem: str | None
    interpreter: str = DEFAULT_INTERPRETER
    trailing: str | None = None


# Text right after the closing `)` that reads as an argument: a word, a path, a
# `$VAR`, or a flag, or a quote that follows whitespace. Operators, redirects,
# comments, a closing `)`, a backtick, `|`, and punctuation are not arguments.
_ARGUMENT_START_RE = re.compile(r"[A-Za-z0-9_$~/-]|\./")
_NOT_ARGUMENT_RE = re.compile(r"\d+[<>]|-->")
_QUOTES = "\"'"
_TRAILING_LIMIT = 60


def _stray_arguments(rest: str) -> str | None:
    """Return the argument-like text at the start of ``rest``, else ``None``.

    ``rest`` is the line after the locator's closing ``)``. Arguments belong inside
    the subshell, right after the script path. Placed here they are a shell syntax
    error, or they never reach the script.
    """
    body = rest.lstrip(" \t")
    if not body or _NOT_ARGUMENT_RE.match(body):
        return None
    spaced = len(body) != len(rest)
    if _ARGUMENT_START_RE.match(body) or (spaced and body[0] in _QUOTES):
        return body[:_TRAILING_LIMIT]
    return None


def find_locators(line: str) -> Iterator[LocatorMatch]:
    """Yield each locator in ``line``, in order.

    A head with no tail after it, or a locator whose script path fails the target
    pattern, yields a match with ``problem`` set and no ``script_rel``. A
    committed locator that no longer reads back is a defect to report, not text to
    skip.
    """
    pos = 0
    while (start := line.find(_PREFIX, pos)) != -1:
        found = _head_at(line, start)
        if found is None:
            rest = line[start + len(_PREFIX) :].split('"', 1)[0].strip()
            end = start + len(_PREFIX)
            yield LocatorMatch(
                start, end, None, "", f"interpreter is not one of {INTERPRETERS}: {rest!r}"
            )
            pos = end
            continue
        interpreter, head = found
        tail_at = line.find(_TAIL, start + len(head))
        if tail_at == -1:
            yield LocatorMatch(
                start, len(line), None, "", "locator has no closing text", interpreter
            )
            return
        end = tail_at + len(_TAIL)
        try:
            script_rel, args = _split_middle(line[start + len(head) : tail_at])
        except LauncherError as exc:
            yield LocatorMatch(start, end, None, "", str(exc), interpreter)
        else:
            trailing = _stray_arguments(line[end:])
            yield LocatorMatch(start, end, script_rel, args, None, interpreter, trailing)
        pos = end
