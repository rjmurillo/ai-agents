#!/usr/bin/env python3
"""The `git ls-files --eol` record: what one looks like, and how it renders.

Split from `check_index_line_endings.py` at the 500-line `file-size` ceiling,
along the seam where the subject changes. Nothing here runs a subprocess or
touches a repository: it turns one producer's bytes into `Violation` values and
turns a tracked pathname into something a UTF-8 log can carry. The gate that
invokes git, decides, reports and remediates is the other module.

The seam is also the test seam. `tests/validation/test_check_index_line_endings.py`
covers this module against strings the test wrote; the two sibling modules cover
the gate against real repositories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `git ls-files --eol` prefixes the stored state with `i/`. `mixed` is included
# because a blob holding both endings is broken the same way a pure-CRLF one
# is; `none` means no line endings at all and cannot contradict anything.
_BAD_INDEX_STATES = frozenset({"i/crlf", "i/mixed"})

# Only these attribute values promise LF in the blob. A path marked `-text` is
# exempt by declaration, and `eol=crlf` asks for CRLF on purpose, so neither is
# a contradiction.
_LF_ATTRIBUTES = ("eol=lf",)

# Control characters that must never reach a log line verbatim: C0 including
# newline, tab, carriage return and ESC, DEL, and the C1 block. A tracked
# pathname may legally contain any of them on POSIX, and a contributor chooses
# the name. Emitted unchanged into a required CI log, a newline forges a log
# line and an ESC sequence rewrites what the reader sees (CWE-117).
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def display_path(path: str) -> str:
    """A path rendered for a UTF-8 log stream, with nothing left that can lie.

    Two classes of byte are escaped, for two different reasons.

    The surrogates that keep a path reversible cannot be written to stdout:
    `print` raises `UnicodeEncodeError` on them. Control characters can be
    written, which is the problem: a tracked path may carry a newline or an
    ESC sequence, and this gate prints paths into a required CI log, so an
    unescaped one forges a log line or repaints the terminal around it
    (CWE-117). Both classes come out as their `\\x` or `\\n` spelling.

    Only the human-facing output is escaped. `--fix` still receives the
    reversible form, so the path the operator reads and the path git receives
    can differ by exactly the bytes that have no safe text spelling. `_report`
    is what keeps that difference from being handed out as a runnable command.
    """
    escaped = path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    return _CONTROL_CHARACTERS.sub(
        lambda match: match.group().encode("unicode_escape").decode("ascii"), escaped
    )


def is_spellable(path: str) -> bool:
    """True when the displayed path is the path, byte for byte.

    A path that survives `display_path` unchanged can be quoted into a command
    an operator can paste. One that does not cannot: `shlex.quote` would quote
    the escaped spelling, which names a different file or no file at all.
    """
    return display_path(path) == path



@dataclass(frozen=True)
class Violation:
    """One tracked path whose stored blob contradicts its attributes."""

    path: str
    index_state: str
    attributes: str
    scope: str = "HEAD"

    def render(self) -> str:
        return (
            f"[CRLF] {display_path(self.path)}: {self.scope} blob is "
            f"{self.index_state} but attributes say {self.attributes}"
        )


def parse_violations(output: str, scope: str = "HEAD") -> tuple[list[Violation], int]:
    """Parse NUL-terminated `git ls-files --eol -z` output.

    Each record is `i/<state> w/<state> attr/<attrs><TAB><path>`. The attribute
    field carries several space-separated values, so the path is split on the
    tab rather than on whitespace: a path containing spaces would otherwise be
    truncated and silently drop a real violation.

    Newline-separated input is accepted too, so a caller holding output from a
    git that predates `-z` still parses. A path containing a literal newline is
    only safe under `-z`, which is why the producer above always passes it.
    """
    violations: list[Violation] = []
    examined = 0
    # Do not strip newlines from a NUL record. A tracked path may legally
    # begin or end with one, and `-z` exists precisely so those survive; a
    # strip here would report a path that does not exist and hand it to --fix.
    nul_terminated = "\0" in output
    records = output.split("\0") if nul_terminated else output.splitlines()
    for record in records:
        line = record if nul_terminated else record.rstrip("\n")
        # `-z` terminates rather than separates, so the split always yields a
        # trailing empty string. That is the one record with nothing in it and
        # the only one worth passing over.
        if not line:
            continue
        # Everything else must be a row this parser understands. Skipping a
        # malformed row would let a producer change turn a broken scan into
        # "0 violations" and exit 0, which is the failure ci-scripts.md MUST-12
        # names: a run that did nothing must not report the same way as a run
        # that succeeded. Raising here reaches the exit-2 path in `main` and
        # the False verdict in the gate, so a format change fails loudly.
        if "\t" not in line:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with no tab: {line!r}. "
                "The parser expects `i/<state> w/<state> attr/<attrs><TAB><path>`."
            )
        head, path = line.split("\t", 1)
        fields = head.split()
        if len(fields) < 3:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with {len(fields)} field(s) "
                f"before the tab, expected at least 3: {line!r}."
            )
        examined += 1
        index_state = fields[0]
        attributes = " ".join(fields[2:])
        if index_state not in _BAD_INDEX_STATES:
            continue
        if not any(token in attributes for token in _LF_ATTRIBUTES):
            continue
        violations.append(
            Violation(
                path=path,
                index_state=index_state,
                attributes=attributes,
                scope=scope,
            )
        )
    return violations, examined
