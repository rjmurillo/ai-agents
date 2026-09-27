#!/usr/bin/env python3
"""Blocking validator: plugin-root skill invocations must use bare ``python3`` (issue #5949).

A skill invokes its own scripts through a plugin-root path so the same
Markdown works whether the skill runs from this checkout or from a vendored
install:

    python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"\
        "/skills/<skill>/scripts/<name>.py"

The repository has standardized on that one form for every such invocation.
Two things have to hold for it to be portable:

1. **The interpreter is exactly ``python3``.** ``uv run python <script>``
   resolves the project's locked virtual environment, but a vendored plugin
   install ships no ``pyproject.toml`` and no lock file for ``uv`` to resolve,
   so that form fails outright in the one place this invocation shape exists
   to support. A bare ``python`` or a pinned ``python3.11`` works today only by
   accident of whatever interpreter happens to be first on ``PATH``.
2. **The target script imports nothing beyond the standard library.** A step
   that runs ``python3 <script>`` (not ``uv run python <script>``) resolves the
   caller's ambient interpreter, which has installed nothing project-specific.
   ``.claude/rules/ci-scripts.md`` MUST-18 states this for CI steps in the same
   words: "A step that invokes a script with bare ``python3`` may import only
   the standard library." The same physics applies to a skill script launched
   this way from inside a vendored install, which has no ``pyproject.toml`` to
   install dependencies from even if it wanted to.

This validator enforces both. It does not carry a baseline: every current
invocation in the repository was migrated to the canonical form in the same
change that added this guard (per issue #5949), so any offense at all is a
regression.

Scope: tracked ``*.md``, ``*.py``, ``*.tmpl``, and ``*.mustache`` files, minus
two exclusions:

* ``tests/`` -- fixtures construct offending invocations on purpose, the same
  carve-out shape as ``tests/hooks/fixtures/`` in ``.claude/rules/universal.md``
  and as the ``tests/`` exclusion in
  ``scripts/validation/check_doc_interpreter_portability.py``.
* ``HISTORICAL_ROOTS`` -- records of what was decided or done, not
  instructions to follow. Imported directly from
  ``scripts/validation/check_doc_interpreter_portability.py`` rather than
  duplicated, so the two guards' notion of "historical" cannot drift apart.

Detection:

  An **invocation** is an interpreter token, optionally followed by short
  options (``-u``, ``-B``), immediately followed by an operand that begins
  with ``${COPILOT_PLUGIN_ROOT`` or ``${CLAUDE_PLUGIN_ROOT`` (quoted or bare).
  The operand's path may be written two ways, both seen in this repository:

      (plugin-root-interpreter: docstring example, illustrative only)
      python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/scripts/y.py"
      (plugin-root-interpreter: docstring example, illustrative only)
      python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"/skills/x/scripts/y.py

  (the first quotes the whole operand; the second closes the quote right after
  the ``${...}`` expansion and leaves the path bare). Both resolve to the same
  file at runtime, so both are recognized.

  **Rule 1 (form).** The interpreter must be exactly ``python3``. Anything
  else -- ``uv run [options] python``, ``uv run [options] python3``, bare
  ``python``, a pinned ``python3.11`` -- is flagged, naming the canonical form.

  **Rule 2 (dependencies).** Only checked for an invocation that already
  satisfies rule 1 (a form violation is reported once, not twice). The plugin
  root's fallback chain resolves to ``.claude`` in this repository, so the
  operand's ``skills/...py`` tail is checked against ``.claude/<tail>``:

  * If that path is not a tracked ``.py`` file, the invocation names a
    dangling target.
  * If it is tracked, ``third_party_imports`` (imported from
    ``check_doc_interpreter_portability``, which walks the module-level import
    closure per its own docstring) must return an empty set. A non-empty
    result names the modules a vendored install's ambient interpreter cannot
    resolve.

  A line carrying ``plugin-root-interpreter:`` plus a reason, on the offending
  line or the line directly above it, suppresses that one offense. Same
  line-scoped shape as ``check_doc_interpreter_portability.py``'s
  ``doc-interpreter-portability:`` marker, and for the same reason: a
  whole-file opt-out hid five real offenses under this guard's older sibling
  before it was narrowed to a line.

  A backslash-newline line continuation is collapsed before matching (so an
  invocation split across lines for readability is still recognized), and the
  reported line number is where the invocation's interpreter token started in
  the original file, not where the operand happened to land.

Exit codes (ADR-035):
  0 - no offenses found
  1 - one or more offenses found
  2 - configuration error (git unavailable, an in-scope tracked file could not
      be read, or the scan examined zero files)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.check_doc_interpreter_portability import (  # noqa: E402
    HISTORICAL_ROOTS,
    ScanError,
    third_party_imports,
    tracked_files,
)

# Fixtures construct offending invocations on purpose. Same carve-out shape as
# ``FIXTURE_ROOTS`` in ``check_doc_interpreter_portability.py``, kept as a
# separate tuple here (rather than imported) because it is the one piece of
# scope this guard does not share verbatim with its sibling: the sibling also
# excludes generated mirrors and a generated-prompt prefix that carry no
# plugin-root invocations of this shape, and importing a bigger tuple than
# this guard needs would be its own kind of drift.
FIXTURE_ROOTS: tuple[str, ...] = ("tests/",)

# Line-scoped opt-out, same shape as `check_doc_interpreter_portability.py`'s
# ``doc-interpreter-portability:`` marker (module docstring above explains why
# line-scoped rather than file-scoped).
DECLARATION = "plugin-root-interpreter:"

# The plugin-root fallback chain used across the repository is
# ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``, so an operand
# that resolves through it lands under ``.claude`` in this checkout.
_PLUGIN_ROOT_FALLBACK = ".claude"
_PLUGIN_ROOT_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")

# One interpreter token: `python`, `python3`, or a pinned `python3.11`-style
# name. Matched identically inside and outside a `uv run` prefix so both
# offending shapes (`uv run python`, bare `python3.11`) are recognized by one
# sub-pattern.
_INTERP_TOKEN = r"python3?(?:\.\d+)?"

# The interpreter phrase, up to and including the opening `${` of a
# plugin-root variable reference. Two alternatives:
#   - `uv run [uv options/values] python[3]` (always a rule-1 violation); the
#     option tokens exclude shell separators so `uv run pytest; python3 ...`
#     stays one canonical invocation, not a `uv run` one
#   - a bare interpreter token (canonical only when it is exactly `python3`)
# Either is optionally followed by short options (`-u`, `-B`), then the
# operand: an optional opening quote, then the literal `${COPILOT_PLUGIN_ROOT`
# or `${CLAUDE_PLUGIN_ROOT`. `\b` stops the variable-name match before the
# `:-` fallback separator so the balanced-brace scan below starts from a known
# position.
_INVOCATION_HEAD = re.compile(
    r"(?<![\w./-])"
    r"(?P<interp>"
    rf"uv[ \t]+run(?:[ \t]+[^\s;&|`]+)*?[ \t]+{_INTERP_TOKEN}"
    r"|"
    rf"{_INTERP_TOKEN}"
    r")"
    r"(?:[ \t]+-[\w-]+)*"
    r"[ \t]+"
    r'(?P<quote>["\'])?'
    r"\$\{(?:" + "|".join(_PLUGIN_ROOT_VARS) + r")\b"
)

# The `skills/...py` tail once the plugin-root expansion is behind us.
_PATH_TAIL = re.compile(r"/skills/[A-Za-z0-9_./-]*\.py")


@dataclass(frozen=True, slots=True)
class _Invocation:
    """One recognized plugin-root invocation on a single logical line."""

    start: int
    interp: str
    tail: str  # e.g. "skills/foo/scripts/bar.py" (leading "/" stripped)


def _match_balanced_braces(line: str, start: int) -> int | None:
    """Return the index just past the ``}`` that closes the brace before ``start``.

    ``start`` is the position right after ``${VARNAME`` was matched, so one
    brace is already open (``depth`` begins at 1). The fallback chain nests one
    level deep (``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``);
    this scans character by character rather than assuming a fixed nesting
    depth, so it tolerates a bare ``${VAR}`` or a deeper chain equally.
    Returns ``None`` when the line ends before the brace closes (malformed or
    truncated input), which the caller treats as "not an invocation".
    """
    depth = 1
    index = start
    length = len(line)
    while index < length:
        char = line[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _find_invocations(line: str) -> Iterator[_Invocation]:
    """Yield every recognized plugin-root invocation on one logical line."""
    pos = 0
    while True:
        match = _INVOCATION_HEAD.search(line, pos)
        if match is None:
            return
        pos = match.end()
        brace_end = _match_balanced_braces(line, match.end())
        if brace_end is None:
            continue
        quote = match.group("quote")
        quote_closes_at_brace = quote is not None and line[brace_end : brace_end + 1] == quote
        path_start = brace_end + 1 if quote_closes_at_brace else brace_end
        tail_match = _PATH_TAIL.match(line, path_start)
        if tail_match is None:
            continue
        tail_end = tail_match.end()
        if quote is not None and not quote_closes_at_brace:
            # Whole-operand quoting: the closing quote must follow the path.
            if line[tail_end : tail_end + 1] != quote:
                continue
        yield _Invocation(
            start=match.start(),
            interp=match.group("interp"),
            tail=tail_match.group(0).lstrip("/"),
        )


def _join_continuations(text: str) -> tuple[list[str], list[list[int]]]:
    """Collapse backslash-newline continuations; keep each char's source line.

    Returns parallel lists: logical lines with continuations joined, and for
    each logical line a same-length list mapping every character index back to
    the 1-indexed original line it came from. A regex match against a logical
    line can then be attributed to the real line the reader would open.
    """
    logical_lines: list[str] = []
    line_no_maps: list[list[int]] = []
    parts: list[str] = []
    char_map: list[int] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.endswith("\\"):
            content = raw[:-1]
            parts.append(content)
            char_map.extend([lineno] * len(content))
            continue
        parts.append(raw)
        char_map.extend([lineno] * len(raw))
        logical_lines.append("".join(parts))
        line_no_maps.append(char_map)
        parts, char_map = [], []
    if parts:  # trailing continuation with no following line to close it
        logical_lines.append("".join(parts))
        line_no_maps.append(char_map)
    return logical_lines, line_no_maps


def _lineno_at(char_map: list[int], index: int) -> int:
    if not char_map:
        return 1
    if index < len(char_map):
        return char_map[index]
    return char_map[-1]


def _is_declared(raw_lines: list[str], lineno: int) -> bool:
    """Return whether ``DECLARATION`` covers the (1-indexed) offending line."""
    for zero_indexed in (lineno - 1, lineno - 2):
        if 0 <= zero_indexed < len(raw_lines) and DECLARATION in raw_lines[zero_indexed]:
            return True
    return False


def is_in_scope(rel_path: str) -> bool:
    """Return whether a file carries invocations this guard should gate."""
    return not rel_path.startswith(FIXTURE_ROOTS + HISTORICAL_ROOTS)


def _form_message(rel: str, lineno: int, interp: str) -> str:
    return (
        f"{rel}:{lineno}: invoke a plugin-root skill script with 'python3', "
        f"not {interp!r} (issue #5949)"
    )


def _dependency_message(
    rel: str, lineno: int, tail: str, repo_root: Path, tracked_py: set[str]
) -> str | None:
    """Return rule-2's message for one canonical-form invocation, or ``None``."""
    mapped = f"{_PLUGIN_ROOT_FALLBACK}/{tail}"
    if mapped not in tracked_py:
        return (
            f"{rel}:{lineno}: {mapped} is not a tracked file "
            f"(dangling plugin-root target, issue #5949)"
        )
    external = sorted(third_party_imports(mapped, repo_root, tracked_py))
    if not external:
        return None
    return (
        f"{rel}:{lineno}: {mapped} imports {', '.join(external)}, which a vendored "
        f"plugin install's bare python3 cannot resolve (issue #5949)"
    )


def find_offenses(
    text: str, rel: str, repo_root: Path, tracked_py: set[str]
) -> list[tuple[int, str]]:
    """Return (line, message) for every offense in one file's already-read text."""
    raw_lines = text.splitlines()
    logical_lines, line_maps = _join_continuations(text)
    offenses: list[tuple[int, str]] = []
    for logical, char_map in zip(logical_lines, line_maps, strict=True):
        for invocation in _find_invocations(logical):
            lineno = _lineno_at(char_map, invocation.start)
            if _is_declared(raw_lines, lineno):
                continue
            if invocation.interp != "python3":
                offenses.append((lineno, _form_message(rel, lineno, invocation.interp)))
                continue
            message = _dependency_message(rel, lineno, invocation.tail, repo_root, tracked_py)
            if message is not None:
                offenses.append((lineno, message))
    return offenses


def scan(repo_root: Path) -> list[str]:
    """Return one message per offense across the whole tracked tree."""
    tracked_py = set(tracked_files(repo_root, "*.py"))
    all_offenses: list[tuple[str, int, str]] = []
    for rel in tracked_files(repo_root, "*.md", "*.py", "*.tmpl", "*.mustache"):
        if not is_in_scope(rel):
            continue
        path = repo_root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ScanError(f"could not read {rel}: {exc}") from exc
        for lineno, message in find_offenses(text, rel, repo_root, tracked_py):
            all_offenses.append((rel, lineno, message))
    all_offenses.sort(key=lambda item: (item[0], item[1]))
    return [message for _, _, message in all_offenses]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Fail when a plugin-root skill invocation uses anything but bare "
            "python3, or names a target with non-stdlib imports (issue #5949)."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the check and print one line per offense plus a summary."""
    args = build_parser().parse_args(argv)
    repo_root = (args.repo_root or Path.cwd()).resolve()

    try:
        tracked_count = len(tracked_files(repo_root, "*.md", "*.py", "*.tmpl", "*.mustache"))
        if tracked_count == 0:
            print(
                "check-plugin-root-interpreter: refusing zero-file scan",
                file=sys.stderr,
            )
            return 2
        offenses = scan(repo_root)
    except (OSError, ScanError, subprocess.CalledProcessError) as exc:
        print(f"check-plugin-root-interpreter: {exc}", file=sys.stderr)
        return 2

    for message in offenses:
        print(message, file=sys.stderr)

    if offenses:
        print(
            f"check-plugin-root-interpreter: FAIL ({len(offenses)} offense(s))",
            file=sys.stderr,
        )
        return 1

    print(f"check-plugin-root-interpreter: OK ({tracked_count} files examined)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
