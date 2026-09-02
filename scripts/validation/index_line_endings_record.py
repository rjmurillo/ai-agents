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

import shlex
import unicodedata
from dataclasses import dataclass

# `git ls-files --eol` prefixes the stored state with `i/`. `mixed` is included
# because a blob holding both endings is broken the same way a pure-CRLF one
# is; `none` means no line endings at all and cannot contradict anything.
_BAD_INDEX_STATES = frozenset({"i/crlf", "i/mixed"})

# Only these attribute values promise LF in the blob. A path marked `-text` is
# exempt by declaration, and `eol=crlf` asks for CRLF on purpose, so neither is
# a contradiction. Matched as whole tokens, never as substrings: `eol=lfx` is
# not a promise of LF and reporting it as one blocks a push over an attribute
# the repository never made.
_LF_ATTRIBUTES = frozenset({"eol=lf"})

# The producer's row contract, one prefix per leading field:
# `i/<state> w/<state> attr/<attrs>`. Checked, not assumed.
_FIELD_PREFIXES = ("i/", "w/", "attr/")

# Unicode categories that must never reach a log line verbatim. A tracked
# pathname may legally carry any of them on POSIX, and a contributor chooses
# the name, so each is contributor-controlled input to a required CI log.
#
# `Cc` is the control category: C0 including newline, tab, carriage return and
# ESC, plus DEL and the C1 block. A newline forges a log line and an ESC
# sequence repaints the terminal around one (CWE-117).
#
# `Cf` is the format category: the bidi controls, zero-width space, ZWNJ, ZWJ,
# soft hyphen, the BOM. Every one renders as nothing or reorders what follows,
# so `handoff‮dm.txt` reads as a different filename than it is (CWE-451).
# The class framing is deliberate, not a list of the variants reported so far:
# `scripts/validation/git_hook_policy.py` reaches the same conclusion for
# placeholder text and states it verbatim as
# `DEBATE_LOG_PLACEHOLDER_FORMAT_CATEGORY = "Cf"`, with the reasoning that its
# own check "was defeated four times on this PR, by invalid bytes, ASCII
# spaces, U+00A0, and markdown escapes. Each fix targeted the variant in front
# of it and the next variant was cheaper than the last."
#
# `Zl` and `Zp` are the line and paragraph separators, U+2028 and U+2029. They
# are not in `Cc`, and a renderer that honours them breaks the line just as a
# newline does.
#
# Stricter/looser/different than canonical: `git_hook_policy.py` normalizes
# `Cf` away before matching, because its subject is whether two strings are the
# same placeholder. This escapes instead, because the path has to stay
# readable and the operator has to see that something invisible is there.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def display_path(path: str) -> str:
    """A path rendered for a UTF-8 log stream, with nothing left that can lie.

    Two classes of character are escaped, for two different reasons.

    The surrogates that keep a path reversible cannot be written to stdout:
    `print` raises `UnicodeEncodeError` on them. Everything in
    `_UNSAFE_CATEGORIES` can be written, which is the problem: it renders as
    something other than itself, and this gate prints contributor-chosen paths
    into a required CI log. Both classes come out as their `\\x`, `\\n` or
    `\\u` spelling.

    This is the display spelling and nothing else. It is deliberately not
    reversible, so it never reaches git: `--fix` passes the surrogate-escaped
    path as argv, and the printed command goes through `shell_argument`, which
    re-encodes the real bytes in a form a shell turns back into them. So one
    path has three renderings on purpose: what the operator reads here, what
    a shell is given, and what git receives.
    """
    escaped = path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    return "".join(
        character.encode("unicode_escape").decode("ascii")
        if unicodedata.category(character) in _UNSAFE_CATEGORIES
        else character
        for character in escaped
    )


def is_spellable(path: str) -> bool:
    """True when the displayed path is the path, byte for byte.

    A path that survives `display_path` unchanged can go through
    `shlex.quote`. One that does not cannot: `shlex.quote` would quote the
    escaped spelling, which names a different file or no file at all.
    `shell_argument` is what decides between the two.
    """
    return display_path(path) == path


def shell_argument(path: str) -> str:
    """One shell argument that reaches git as the exact bytes of `path`.

    `shlex.quote` handles anything with a text spelling, which is nearly every
    path and the only form POSIX `sh` can express. It cannot express a byte
    with no text spelling, and quoting the escaped display form would name a
    different file, so those paths get bash and zsh's ANSI-C form instead:
    `$'bad\\xff.md'` puts byte 0xff into argv. Every byte outside printable
    ASCII is escaped, and so are `'` and `\\`, which are the two characters
    that would otherwise end or alter the quoting.

    A caller that prints this has to say which shells the second form needs.
    `_print_paste_command` does.
    """
    if is_spellable(path):
        return shlex.quote(path)
    body = "".join(
        chr(byte) if 0x20 <= byte < 0x7F and chr(byte) not in "'\\" else f"\\x{byte:02x}"
        for byte in path.encode("utf-8", "surrogateescape")
    )
    return f"$'{body}'"


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
    for position, record in enumerate(records):
        line = record if nul_terminated else record.rstrip("\n")
        # `-z` terminates rather than separates, so the split always yields one
        # trailing empty string. That is the only record with nothing in it
        # that this producer can legitimately emit, and only in last position.
        # A leading or interior empty record means the producer emitted a row
        # this parser cannot read, and passing over it turns malformed output
        # into a clean scan: `parse_violations("\0")` returned zero violations
        # in zero files, which is what an empty repository returns too.
        if not line:
            if position == len(records) - 1:
                continue
            raise RuntimeError(
                f"git ls-files --eol emitted an empty record at position "
                f"{position} of {len(records)}. Only the trailing record after "
                "the final NUL may be empty."
            )
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
        if not path:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with an empty path: {line!r}. "
                "Git cannot track one, so this row means the parser has stopped "
                "understanding the producer."
            )
        fields = head.split()
        if len(fields) < 3:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with {len(fields)} field(s) "
                f"before the tab, expected at least 3: {line!r}."
            )
        # Counting the fields is not reading them. A row spelled
        # `x/crlf y/crlf z/text eol=lf` has three fields and no meaning here:
        # `index_state` would never match `_BAD_INDEX_STATES` and the row would
        # be passed over as clean, which is the same MUST-12 silent pass the
        # tab and field-count checks above exist to prevent. The prefixes are
        # the producer's contract, so they are what gets checked.
        for field, prefix in zip(fields[:3], _FIELD_PREFIXES, strict=True):
            if not field.startswith(prefix):
                raise RuntimeError(
                    f"git ls-files --eol emitted a row whose field {field!r} does "
                    f"not start with {prefix!r}: {line!r}. The parser expects "
                    "`i/<state> w/<state> attr/<attrs><TAB><path>`."
                )
        examined += 1
        index_state = fields[0]
        attributes = " ".join(fields[2:])
        if index_state not in _BAD_INDEX_STATES:
            continue
        # `attr/` prefixes the first attribute only, so it comes off before the
        # comparison. The rest are already bare tokens.
        declared = {fields[2].removeprefix("attr/"), *fields[3:]}
        if not declared & _LF_ATTRIBUTES:
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
