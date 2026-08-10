"""Bounded shell expansion for the push-pr identity guard (issue #4764).

Answers one question for the relevance gate: can this command text name
``new_pr.py`` once bash finishes expanding it? Brace groups, extglob groups,
and ANSI-C quoting all rewrite text before execution, so the guard reproduces
them under an explicit budget rather than trusting the literal spelling.

Two budgets bound the work, and both are required. ``_MAX_BRACE_EXPANSIONS``
caps how many alternatives are materialized; ``_MAX_BRACE_EXPANDED_BYTES``
caps their total size, because every alternative carries a copy of the
surrounding literal text and a count budget alone cannot bound bytes
(issue #4764 measured a 195.6 MiB peak inside the count budget).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator

from _push_pr_guard_lex import (
    _NEW_PR_TARGET,
    GuardViolationError,
    ShellToken,
    _could_target_new_pr,
    _split_command,
    _split_shell_segments,
    _strip_unquoted_redirections,
)

_INNERMOST_BRACE_GROUP = re.compile(r"\{([^{}]*)\}")


# Bash extglob group: one of ? * + @ ! immediately followed by a
# parenthesized alternation. Innermost only, so nesting is handled by repeated
# application rather than by a recursive pattern.
_EXTGLOB_GROUP = re.compile(r"([?*+@!])\(([^()]*)\)")


_COMMAND_SUBSTITUTION = re.compile(r"\$\([^()]*\)|`[^`]*`")


_ANSI_C_QUOTED = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


_MAX_BRACE_EXPANSIONS = 4096


# Total bytes one relevance decision may materialize across all brace
# expansions. The count budget above cannot bound this: every expansion carries
# a copy of the surrounding literal text, so cost is count times length. Issue
# #4764 measured 204,832,768 bytes and a 195.6 MiB peak from a 100,060-byte
# command that never exceeded the count budget. 256 KiB leaves ordinary
# multi-alternative commands untouched while keeping a hostile 128 KiB command
# far from both the host's 10s PreToolUse timeout (where a Copilot timeout
# fails OPEN) and any meaningful RSS growth.
_MAX_BRACE_EXPANDED_BYTES = 256 * 1024


# Bound on innermost-first extglob rewrites, so a pathological nesting cannot
# loop. Far above any real command; the canonical invocation has none.
_MAX_EXTGLOB_REWRITES = 64


def _brace_alternatives(body: str) -> list[str]:
    """Return the alternatives a single innermost brace group can produce.

    A range is not materialized. Only values that can contribute a character
    of the target matter for the relevance decision, so a range collapses to
    at most the target's own alphabet plus one representative:

    * Digits appear nowhere in "new_pr.py", so a numeric range can never supply
      a character the target needs. It can only shift later text by its own
      width, and the narrowest and widest values bound that.
    * A character range can supply a needed character, so keep exactly the
      characters the target contains, plus the low value to represent every
      choice that lands outside a match.

    Bash's optional step (``{start..end..step}``) is parsed and then ignored.
    A step only removes values from the range, so collapsing against the full
    range stays a superset of what the shell produces, which is the safe
    direction: relevance may over-include, never under-include. Missing the
    step let ``./attacker/pr/n{e..e..1}w_pr.py`` read as literal text and skip
    the guard entirely (issue #4825).

    Materializing instead would make ``touch log{0..99}.txt`` and
    ``cp file{1..1000}.txt dir/`` exceed the expansion budget and fail closed,
    which denied legitimate commands (measured 4 of 7 in a probe).
    """
    bounds = body.split("..")
    if len(bounds) in {2, 3}:
        start, end = bounds[0], bounds[1]
        if start and end:
            if start.isdigit() and end.isdigit():
                low, high = sorted((int(start), int(end)))
                return sorted({str(low), str(high)})
            if len(start) == 1 and len(end) == 1:
                low, high = sorted((ord(start), ord(end)))
                candidates = {
                    chr(point) for point in range(low, high + 1) if chr(point) in _NEW_PR_TARGET
                }
                candidates.add(chr(low))
                return sorted(candidates)
    return body.split(",")


class _ExpansionBudgetError(Exception):
    """Enumeration hit a bound before finishing, so the caller must fail closed.

    A distinct type rather than a ``None`` return, so a caller cannot mistake
    "produced no match" for "gave up before looking". The two demand opposite
    verdicts: the first means the command is irrelevant, the second means the
    guard cannot prove it is, and an attacker who can force the second reading
    into an allow buys a bypass by making the command expensive.
    """


def _iter_brace_expansions(command: str) -> Iterator[str]:
    """Yield brace expansions of ``command``, innermost group first.

    Streams instead of materializing, and charges every projected byte against
    a budget BEFORE allocating it. Issue #4764 measured the previous
    list-building form on the merged tree:

        input 10,921 bytes -> 256 expansions, 2,562,194 bytes materialized
        input 100,060 bytes -> 2,048 expansions, 204,832,768 bytes,
                               195.6 MiB peak allocation

    Both stayed inside the 4,096-expansion budget, because a count budget
    cannot bound size: each expansion carries a full copy of the surrounding
    literal text, so cost is count times length, not count. The byte budget is
    the one that binds, and it is checked against the projected total before
    the strings exist, since checking after allocation measures a spike that
    has already happened.

    Raises ``_ExpansionBudgetError`` when either budget is exhausted. The
    enumeration is deliberately a superset of what a shell produces: relevance
    may over-include, never under-include.
    """
    frontier = [command]
    produced_bytes = len(command)
    remaining = _MAX_BRACE_EXPANSIONS
    while frontier:
        candidate = frontier.pop()
        group = _INNERMOST_BRACE_GROUP.search(candidate)
        if group is None:
            yield candidate
            continue
        alternatives = _brace_alternatives(group.group(1))
        remaining -= len(alternatives)
        if remaining < 0:
            raise _ExpansionBudgetError("brace expansion count budget exhausted")
        base_length = len(candidate) - (group.end() - group.start())
        produced_bytes += sum(base_length + len(alternative) for alternative in alternatives)
        if produced_bytes > _MAX_BRACE_EXPANDED_BYTES:
            raise _ExpansionBudgetError("brace expansion byte budget exhausted")
        frontier.extend(
            candidate[: group.start()] + alternative + candidate[group.end() :]
            for alternative in alternatives
        )


def _extglob_to_brace(text: str) -> str:
    """Rewrite Bash extglob groups into brace groups the expander already handles.

    Issue #4764: ``bash -O extglob`` expands
    ``.../pr/@(new)_pr.py`` to ``.../pr/new_pr.py``, and both dispatchers
    returned 0 (allow) for that command on the merged tree. ``@(`` and ``!(``
    carry none of the ``? * [`` characters the guard treated as glob markers,
    so the pattern read as ordinary literal text that did not contain
    ``new_pr.py``, and ``(`` made the segment fail to tokenize, which routed it
    to a backstop that only inspects the head word.

    Rewriting rather than adding a second expander keeps one enumeration engine
    and one budget. The mapping is a superset of what the shell produces, which
    is the safe direction for a relevance decision:

    ==========  =============  =================================
    Pattern     Rewrite        Reason
    ==========  =============  =================================
    ``@(a|b)``  ``{a,b}``      exactly one alternative
    ``+(a|b)``  ``{a,b}``      one or more; one alternative is in the set
    ``?(a|b)``  ``{,a,b}``     zero or one
    ``*(a|b)``  ``{,a,b}``     zero or more; both endpoints are in the set
    ``!(a|b)``  ``*``          anything else, so a wildcard covers it
    ==========  =============  =================================

    ``*(a|b)`` can also produce ``aa`` and ``abab``, which this does not
    enumerate. It does not need to: relevance asks whether the pattern CAN name
    new_pr.py, and if it can, one of the listed alternatives already spells it.

    Innermost-first, bounded by ``_MAX_EXTGLOB_REWRITES``, so a nested pattern
    cannot loop. Text with no extglob group is returned unchanged.
    """
    for _ in range(_MAX_EXTGLOB_REWRITES):
        match = _EXTGLOB_GROUP.search(text)
        if match is None:
            return text
        operator, body = match.group(1), match.group(2)
        alternatives = body.split("|")
        if operator == "!":
            replacement = "*"
        elif operator in {"?", "*"}:
            replacement = "{," + ",".join(alternatives) + "}"
        else:
            replacement = "{" + ",".join(alternatives) + "}"
        text = text[: match.start()] + replacement + text[match.end() :]
    return text


def _spellings(text: str) -> set[str]:
    """Return the ways a shell could spell ``text`` before it reaches the OS.

    Collects the obfuscations the guard already knew about individually:
    single-character glob classes (``n[e]w_pr.py``), ANSI-C quoting
    (``$'new\\x5fpr.py'``), and extglob groups (``@(new)_pr.py``). Brace
    expansion is applied by the caller, because it is the only one that can
    exceed a budget.
    """
    unclassed = text.replace("[", "").replace("]", "")
    variants = {text, unclassed}
    variants |= {_ansi_c_decoded(variant) for variant in tuple(variants)}
    variants |= {_extglob_to_brace(variant) for variant in tuple(variants)}
    return variants


def _names_new_pr(command: str) -> bool:
    """True when ``command`` text can spell new_pr.py anywhere in it.

    Substring-based and position-blind. Used for CODE positions, where the text
    is a program rather than a path, and by the fail-closed backstop for a
    segment that will not tokenize. Path positions use
    ``_path_names_new_pr`` instead, because a substring test reports
    ``tests/test_new_pr.py`` as new_pr.py (issue #4764).
    """
    for text in _spellings(command):
        if _could_target_new_pr(text):
            return True
        try:
            if any(_could_target_new_pr(candidate) for candidate in _iter_brace_expansions(text)):
                return True
        except _ExpansionBudgetError:
            return True
    return False


def _path_names_new_pr(value: str) -> bool:
    """True when ``value`` is a path whose final component is new_pr.py.

    Basename equality, not substring containment. Issue #4764 measured the
    substring form denying ``python3 -m pytest tests/test_new_pr.py``, because
    ``test_new_pr.py`` contains ``new_pr.py``. A path names the script only
    when its LAST component is the script; ``foo_new_pr.py`` and
    ``new_pr.py.bak`` are different files.

    Narrowing here does not lose the renamed-copy case: a file whose name
    differs but whose bytes match is caught by ``_operand_is_new_pr_copy``,
    which compares content at execution positions.
    """
    for text in _spellings(value):
        try:
            candidates = list(_iter_brace_expansions(text))
        except _ExpansionBudgetError:
            return True
        for candidate in candidates:
            literal = candidate.replace("\\\r\n", "").replace("\\\n", "").casefold()
            for normalized in (literal, literal.replace("\\", "/"), literal.replace("\\", "")):
                compacted = normalized.translate(str.maketrans("", "", "'\"+ \t"))
                basename = compacted.rsplit("/", 1)[-1]
                if basename == _NEW_PR_TARGET:
                    return True
                if any(marker in basename for marker in "?*[") and fnmatch.fnmatch(
                    _NEW_PR_TARGET, basename
                ):
                    return True
    return False


def _ansi_c_decoded(text: str) -> str:
    """Decode Bash ANSI-C ``$'...'`` segments so naming sees what runs.

    Bash executes ``./attacker/pr/$'new\\x5fpr.py'`` as
    ``./attacker/pr/new_pr.py``. The compaction below strips the backslash
    without decoding the escape, producing ``newx5fpr.py``, so a direct launch
    missed every relevance rule (issue #4825). Octal (``\\137``) has the same
    shape.
    """

    def decode(match: re.Match[str]) -> str:
        body = match.group(1)
        try:
            return body.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
            return body

    # Annotated because the generated shim inlines this module into a
    # function, which loses the pattern's inferred type and makes the
    # substitution read as Any to mypy.
    decoded: str = _ANSI_C_QUOTED.sub(decode, text)
    return decoded


def _segment_head_names_new_pr(segment: str) -> bool:
    """Fail-closed backstop for a segment that still will not tokenize.

    Keeps an unparseable but target-shaped execution in scope rather than
    letting a quoting artifact decide relevance.

    Position-blind on purpose. Everywhere else relevance asks WHERE the name
    appears, but a segment that will not tokenize has no positions to ask
    about: the guard cannot tell an operand from a command word in text it
    could not parse. So the whole segment is tested, which is the merged
    tree's original rule confined to the one case that needs it. Testing only
    the head word let ``python3 .../new_pr.py # comment`` out of scope, because
    ``#`` makes ``_split_command`` raise and the head is ``python3``
    (issue #4764).
    """
    stripped = segment.strip()
    if not stripped:
        return False
    if _names_new_pr(stripped):
        return True
    head = stripped.split(None, 1)
    word = head[0].strip("'\"")
    basename = word.rsplit("/", 1)[-1]
    if not basename:
        return False
    return any(marker in basename for marker in "?*[") and fnmatch.fnmatch(_NEW_PR_TARGET, basename)


def _scope_segments(command: str) -> list[list[ShellToken]]:
    """Tokenize each shell segment for the relevance decision only.

    ``_split_command`` rejects command substitution, shell operators and
    redirections as policy. Those rejections must not decide relevance:
    returning nothing on a parse failure failed open, so appending ``&& true``
    or ``>out`` defeated every execution-position rule (issue #4825).

    Substitutions are neutralized, redirections dropped, and the command split
    on unquoted operators, because execution position is a per-segment
    property. A segment that still will not parse is reported through the
    fail-closed backstop rather than silently skipped.
    """
    neutralized = _COMMAND_SUBSTITUTION.sub("$X", command)
    segments: list[list[ShellToken]] = []
    for piece in _split_shell_segments(_strip_unquoted_redirections(neutralized)):
        stripped = piece.strip()
        if not stripped:
            continue
        # Extglob groups become brace groups BEFORE tokenizing. `(` and `)` are
        # shell operators that _split_command rejects, so an extglob segment
        # used to fail to parse and fall through to the head-word backstop,
        # which allowed `python3 .../@(new)_pr.py` outright (issue #4764).
        # Rewriting keeps one expansion engine and one budget; see
        # _extglob_to_brace for the mapping and why it is a safe superset.
        rewritten = _extglob_to_brace(stripped)
        try:
            tokens = _split_command(rewritten)
        except GuardViolationError:
            if _segment_head_names_new_pr(rewritten):
                return [[ShellToken(_NEW_PR_TARGET, _NEW_PR_TARGET)]]
            continue
        if tokens:
            segments.append(tokens)
    return segments
