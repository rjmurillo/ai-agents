"""Canonical: scripts/hook_utilities/lsp_symbols.py. Sync via scripts/sync_plugin_lib.py.

Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT, v2.3.2),
file ``kit/hooks/lsp-first-guard.js``, function ``isCodeSymbol``. PURE module:
input is a string, output is a boolean; no side effects.

Canonical kit ``isCodeSymbol`` (``lsp-first-guard.js:64-99``), quoted
character-for-character (canonical-source-mirror.md). The Python regexes below
reproduce these patterns; this block is the authority:

    function isCodeSymbol(s) {
      if (s.length < 4) return false;
      if (/\\s/.test(s)) return false;
      if (/[&?+[\\]{}()\\\\^$*]/.test(s)) return false;

      const allowList = [
        /^(TODO|FIXME|HACK|XXX|NOTE)/i,
        /^console\\./, /^import\\b/, /^require\\(/, /^from\\b/, /^export\\b/,
        /^\\/\\//, /^#/, /^\\./, /^http/i, /^\\d/,
        /^[A-Z_]{3,}$/,
        /^[a-z]{1,8}$/,
        /^['"`]/,
        /^use (client|server)/,
      ];
      if (allowList.some(rx => rx.test(s))) return false;

      if (/^[a-z]+-[a-z]/.test(s)) {
        // ...Tailwind allowlist and knowledge-vault component allowlist...
        return false;
      }

      const isCamelCase = /^[a-z][a-zA-Z0-9]{3,}$/.test(s) && /[A-Z]/.test(s);
      const isPascalCase = /^[A-Z][a-zA-Z][a-zA-Z0-9]{2,}$/.test(s);
      const isDottedSymbol = /^[a-z][a-zA-Z]*\\.[a-z][a-zA-Z]*$/i.test(s);
      const isSnakeCaseFunc = /^[a-z]+(_[a-z]+){2,}$/.test(s) && s.length >= 9;

      return isCamelCase || isPascalCase || isDottedSymbol || isSnakeCaseFunc;
    }

Canonical kit ``bash-grep-block.js`` grep helpers, quoted character-for-character
(``bash-grep-block.js:13, 27-28``):

    const ZERO_WIDTH = /[\\u00AD\\u200B-\\u200F\\u2060-\\u2064\\uFEFF]/g;
    if (!/\\b(grep|rg|ag|ack)\\b/i.test(cmd)) process.exit(0);
    if (/\\bgit\\s+grep\\b/i.test(cmd)) process.exit(0);

Stricter/looser/different than canonical
----------------------------------------
- DROPPED Tailwind allowlist: the kit's ``/^[a-z]+-[a-z]/`` branch carries a
  long Tailwind utility-class denylist (``text-``, ``bg-``, ...) and a
  component-suffix allowlist (``-modal``, ``-form``, ...). This repo has no
  Tailwind and no knowledge-vault component vocabulary, so the entire kebab-case
  branch collapses to ``return False`` (a kebab-case token is never a code
  symbol here). This is LOOSER classification (fewer kebab strings flagged) and
  intentional: the false-positive tail the Tailwind list guarded against does
  not exist in this corpus.
- DROPPED bash-grep block set extras: ADR-062 Implementation Notes bind the
  blocked set to grep, rg, egrep, fgrep, ag, ack (and git grep always allowed).
  The kit's ``\\b(grep|rg|ag|ack)\\b`` is extended here to include egrep/fgrep
  per the ADR. This is STRICTER (more binaries gated).
- The pattern/target extraction (``extract_pattern_and_target``) is a Python
  re-expression of the kit's bash command parsing
  (``bash-grep-block.js:32-49``), kept here so the guard stays thin.
"""

from __future__ import annotations

import re

# Zero-width / formatting chars that would split tokens invisibly and bypass
# ASCII regex symbol detection. Kit: ``bash-grep-block.js:13`` (verbatim class).
_ZERO_WIDTH = re.compile(r"[­​-‏⁠-⁤﻿]")

# Disallowed regex-metacharacter set. Kit: ``/[&?+[\]{}()\\^$*]/``.
_HAS_METACHAR = re.compile(r"[&?+\[\]{}()\\^$*]")
_HAS_WHITESPACE = re.compile(r"\s")

# Allowlist (kit ``allowList``, verbatim semantics). A token matching any of
# these is NOT a code symbol.
_ALLOW_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(TODO|FIXME|HACK|XXX|NOTE)", re.IGNORECASE),
    re.compile(r"^console\."),
    re.compile(r"^import\b"),
    re.compile(r"^require\("),
    re.compile(r"^from\b"),
    re.compile(r"^export\b"),
    re.compile(r"^//"),
    re.compile(r"^#"),
    re.compile(r"^\."),
    re.compile(r"^http", re.IGNORECASE),
    re.compile(r"^\d"),
    re.compile(r"^[A-Z_]{3,}$"),
    re.compile(r"^[a-z]{1,8}$"),
    re.compile(r"^['\"`]"),
    re.compile(r"^use (client|server)"),
)

# Kebab-case detection (kit branch entry ``/^[a-z]+-[a-z]/``). In this port the
# whole branch returns False (Tailwind/component allowlists dropped).
_KEBAB_CASE = re.compile(r"^[a-z]+-[a-z]")

# Positive symbol shapes (kit verbatim).
_CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]{3,}$")
_HAS_UPPER = re.compile(r"[A-Z]")
_PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z][a-zA-Z0-9]{2,}$")
_DOTTED_SYMBOL = re.compile(r"^[a-z][a-zA-Z]*\.[a-z][a-zA-Z]*$", re.IGNORECASE)
_SNAKE_CASE_FUNC = re.compile(r"^[a-z]+(_[a-z]+){2,}$")

# Bash grep family: grep, rg, egrep, fgrep, ag, ack (ADR-062 blocked set).
_GREP_FAMILY = re.compile(r"\b(grep|rg|egrep|fgrep|ag|ack)\b", re.IGNORECASE)
_GIT_GREP = re.compile(r"\bgit\s+grep\b", re.IGNORECASE)

# Pattern extraction from a grep command (kit ``patternMatch``, adapted to the
# extended binary set). Quoted-pattern forms first, then a bare-PascalCase form.
_GREP_DOUBLE_QUOTED = re.compile(
    r"\b(?:grep|rg|egrep|fgrep|ag|ack)\s+(?:-\S+\s+)*\"([^\"]+)\"",
    re.IGNORECASE,
)
_GREP_SINGLE_QUOTED = re.compile(
    r"\b(?:grep|rg|egrep|fgrep|ag|ack)\s+(?:-\S+\s+)*'([^']+)'",
    re.IGNORECASE,
)
_GREP_BARE_PASCAL = re.compile(
    r"\b(?:grep|rg|egrep|fgrep|ag|ack)\s+(?:(?:-\w+\s+(?:[a-z]+\s+)?)*?)([A-Z][a-zA-Z]\w+)",
    re.IGNORECASE,
)

# Regex metacharacters stripped from an extracted pattern part before symbol
# classification (kit ``replace(/[*+?^${}()[\]\\]/g, '')``).
_STRIP_METACHARS = re.compile(r"[*+?^${}()\[\]\\]")


def strip_zero_width(s: object) -> str:
    """Remove zero-width / formatting chars (kit ``ZERO_WIDTH`` strip).

    Accepts ``object`` and fails open (returns "") for non-string input, since
    hook payloads are untrusted JSON that may carry non-string values.
    """
    if not isinstance(s, str) or not s:
        return ""
    return _ZERO_WIDTH.sub("", s)


def is_code_symbol(s: object) -> bool:
    """Return True if ``s`` looks like a code symbol (kit ``isCodeSymbol``).

    Faithful port: length floor, whitespace/metachar rejection, allowlist, then
    camelCase / PascalCase / dotted / snake-case (>= 9 chars) recognition. The
    kebab-case branch returns False (Tailwind allowlist dropped; see docstring).
    """
    if not isinstance(s, str):
        return False
    if len(s) < 4:
        return False
    if _HAS_WHITESPACE.search(s):
        return False
    if _HAS_METACHAR.search(s):
        return False

    if any(rx.search(s) for rx in _ALLOW_LIST):
        return False

    # Kit's kebab-case branch: Tailwind/component allowlists dropped here, so a
    # kebab-case token is never a code symbol in this corpus.
    if _KEBAB_CASE.search(s):
        return False

    is_camel = bool(_CAMEL_CASE.search(s)) and bool(_HAS_UPPER.search(s))
    is_pascal = bool(_PASCAL_CASE.search(s))
    is_dotted = bool(_DOTTED_SYMBOL.search(s))
    is_snake = bool(_SNAKE_CASE_FUNC.search(s)) and len(s) >= 9

    return is_camel or is_pascal or is_dotted or is_snake


def is_grep_search(command: object) -> bool:
    """True if ``command`` invokes a blocked grep-family binary.

    Kit: ``/\\b(grep|rg|ag|ack)\\b/i`` extended to egrep/fgrep per ADR-062.
    Zero-width chars are stripped first to prevent ``grep\\u200BFoo`` evasion.
    Accepts ``object`` and fails open (False) for non-string input.
    """
    if not isinstance(command, str) or not command:
        return False
    cleaned = strip_zero_width(command)
    return bool(_GREP_FAMILY.search(cleaned))


def is_git_grep(command: object) -> bool:
    """True if ``command`` is a ``git grep`` (history search, always allowed).

    Kit: ``/\\bgit\\s+grep\\b/i`` (``bash-grep-block.js:28``).
    Accepts ``object`` and fails open (False) for non-string input.
    """
    if not isinstance(command, str) or not command:
        return False
    return bool(_GIT_GREP.search(strip_zero_width(command)))


def extract_pattern_and_target(command: object) -> tuple[list[str], str]:
    """Extract candidate symbol parts and the raw target text from a grep cmd.

    Ports the kit's pattern extraction (``bash-grep-block.js:32-49``): match the
    grep pattern (double-quoted, single-quoted, or bare PascalCase), then split
    on ``|`` and ``.`` and strip metacharacters from each part. Returns the
    cleaned non-empty parts and the original (zero-width-stripped) command so a
    guard can apply ``is_code_symbol`` per part and inspect paths.

    Returns:
        ``(parts, command)`` where ``parts`` may be empty (no extractable
        pattern) and ``command`` is the zero-width-stripped input.
    """
    if not isinstance(command, str) or not command:
        return [], ""
    cleaned_cmd = strip_zero_width(command)
    unescaped = cleaned_cmd.replace('\\"', '"')

    match = (
        _GREP_DOUBLE_QUOTED.search(unescaped)
        or _GREP_SINGLE_QUOTED.search(unescaped)
        or _GREP_BARE_PASCAL.search(unescaped)
    )
    if match is None:
        return [], cleaned_cmd

    full_pattern = match.group(1)
    raw_parts = re.split(r"\\?\||\.", full_pattern)
    parts: list[str] = []
    for raw in raw_parts:
        part = _STRIP_METACHARS.sub("", strip_zero_width(raw)).strip()
        if part:
            parts.append(part)
    return parts, cleaned_cmd
