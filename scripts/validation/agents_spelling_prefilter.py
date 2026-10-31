"""Cheap test for whether a Python source can hold a ``.agents`` finding.

``check_agents_write_targets.scan_python`` walks the AST of every tracked Python
file. Most files cannot name ``.agents`` at all, so the walks are skipped for
them. The test must never answer False for a file the full scan would flag.
"""

from __future__ import annotations

import re

# Prefilter for scan_python. A finding needs a string constant whose decoded value holds
# ".agents" (or the opt-out marker text). Source can spell such a constant without the
# literal substring in two ways, so a bare ``".agents" in text`` check would be unsound:
#   - an escape that decodes to one of the characters ``. a g e n t s``, such as
#     ``"\x2eagents/x"``, ``\u``, ``\U``, ``\N{...}``, or an octal escape, and
#   - implicit concatenation of adjacent literals such as ``".age" "nts/x"``, or a backslash
#     line continuation inside one literal, with string prefixes, parentheses, or
#     comments between the pieces.
# Both patterns over-approximate: a false match only costs the full scan, never a verdict.
_AGENTS_CHARS_HEX = r"(?:2[eE]|61|65|67|6[eE]|73|74)"
_DECODING_ESCAPE = re.compile(
    rf"\\(?:x{_AGENTS_CHARS_HEX}|u00{_AGENTS_CHARS_HEX}|U000000{_AGENTS_CHARS_HEX}"
    r"|N|0?(?:56|141|145|147|156|163|164))"
)
_PIECE_GAP = r"(?:(?:\\(?:\r\n|\r|\n))+|[\"'](?:[\s\\()rRuUfF\"']|#[^\n]*)*[\"'])?"
_SPLIT_AGENTS = re.compile(_PIECE_GAP.join(re.escape(ch) for ch in ".agents"))
_MARKER_TEXT = "agents-write-target"


def may_name_agents(text: str) -> bool:
    """False only when no finding is possible, so the walks can be skipped.

    ``ast.parse`` still runs first: a syntax error must keep failing the gate.
    """
    return (
        ".agents" in text
        or _MARKER_TEXT in text
        or _DECODING_ESCAPE.search(text) is not None
        or _SPLIT_AGENTS.search(text) is not None
    )
