"""Here-document recognition for the Bash scrubber (issue #6624).

Split from ``scan_bash_lexer.py`` to keep that module under the file-size limit.
Finds here-document openers, decides whether the body is inert text, and spots
the terminator line.
"""

import re
from collections import deque
from dataclasses import dataclass, replace

# A here-document opener: `<<`, optional `-`, then the delimiter word. Groups
# 2 to 4 are the quoted forms ('X', "X", \X); group 5 is a bare word.
# A bare word is any run of non-metacharacters, so `<<!`, `<<1`, and `1<<2` are
# openers, as in bash. Arithmetic shifts are screened out by the lexer mode.
_HEREDOC_RE = re.compile(
    r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\([^\s;|&<>()'\"\\$`]+)"
    r"|([^\s;|&<>()'\"\\$`]+))"
)


@dataclass(frozen=True, slots=True)
class Heredoc:
    """One pending here-document: where its body ends and whether it is inert text.

    `inert` is set for a quoted delimiter whose body only inert readers consume. The body
    never expands, so the scrubber blanks it.
    """

    delimiter: str
    strip_tabs: bool
    inert: bool


def begin_heredoc(line: str, i: int, out: list[str], pending: deque[Heredoc]) -> int:
    """Consume `<<` at `i`; queue a here-document when a delimiter word follows.

    `<<<` is a here-string, not a here-document. The delimiter word itself is
    left for the normal lexer, which handles its quotes.
    """
    if line.startswith("<<<", i):
        out.append("<<<")
        return i + 3
    match = _HEREDOC_RE.match(line, i)
    if match:
        dash, single, double, escaped, bare = match.groups()
        quoted = single is not None or double is not None or escaped is not None
        word = next(w for w in (single, double, escaped, bare) if w is not None)
        pending.append(Heredoc(word, dash == "-", quoted))
    out.append("<<")
    return i + 2


def is_terminator(line: str, heredoc: Heredoc) -> bool:
    """A body ends at a line equal to the delimiter. Trailing blanks do not match."""
    text = line.rstrip("\n")
    if heredoc.strip_tabs:
        text = text.lstrip("\t")
    return text == heredoc.delimiter


# Commands that only store, filter, or print a here-document body. A quoted body
# stays inert only when every command on the opener line is one of these. Any
# other command (su, sudo -i, runuser, chroot, at, source, a shell, a variable
# command word) may run the body, so its lines stay on the per-line scan.
_INERT_READERS = frozenset(
    {
        ":", "true", "echo", "printf", "cat", "tee", "read", "mapfile", "readarray",
        "grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk", "jq", "wc", "sort",
        "uniq", "head", "tail", "tr", "cut", "base64", "git", "gh",
        "python", "python3", "node", "perl", "ruby",
    }
)  # fmt: skip

_SEGMENT_SPLIT_RE = re.compile(r"([;|()`]|(?<![<>])&)")
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_REDIRECT_RE = re.compile(r"[0-9]*[<>]")


def _command_word(segment: str) -> str | None:
    """First word of a segment that is not an assignment or a redirection.

    A bare redirection operator (`>`, `2>>`) also skips its target. Returns
    None when no command word is visible, as when a quoted command word was
    blanked by the scrubber.
    """
    skip_next = False
    for token in segment.split():
        if skip_next:
            skip_next = False
        elif _REDIRECT_RE.fullmatch(token):
            skip_next = True
        elif token.startswith(("<", ">")) or _REDIRECT_RE.match(token):
            continue
        elif _ASSIGNMENT_RE.match(token):
            continue
        else:
            return token.rsplit("/", 1)[-1]
    return None


def _consumers(opener: str) -> list[str]:
    """Segments that can consume the body: the one holding `<<`, those after it,
    and the enclosing command of a substitution (`eval $(cat <<'EOF'`).

    Commands before a `;`, `&`, or `|` boundary never read the body.
    """
    parts = _SEGMENT_SPLIT_RE.split(opener)
    segments, seps = parts[0::2], parts[1::2]
    owner = next((i for i, seg in enumerate(segments) if "<<" in seg), None)
    if owner is None:
        return []
    first = owner
    while first > 0 and seps[first - 1] in ("(", "`"):
        first -= 1
    return segments[first:]


def _feeds_shell(opener: str) -> bool:
    """True unless the opener line shows only inert readers consuming the body.

    Fails closed: the segment holding the here-document must name a known inert
    reader, and so must every other consuming segment that names a command. An
    unknown or hidden command word keeps the body on the per-line scan. Segments
    split on `;`, `&`, `|`, parentheses, and backticks, so `eval $(cat <<'EOF'`
    and `cat <<'EOF' | bash` both name a reader outside the list.
    """
    segments = _consumers(opener)
    if not segments:
        return True
    owner = next(s for s in segments if "<<" in s)
    if _command_word(owner) not in _INERT_READERS:
        return True
    return any(
        word is not None and word not in _INERT_READERS for word in map(_command_word, segments)
    )


def mark_shell_fed(pending: deque[Heredoc], opener: str) -> deque[Heredoc]:
    """Return `pending` with bodies a shell reads no longer inert.

    A quoted delimiter stops the outer shell from expanding the body. When the
    opener line passes the body to anything but a known inert reader (a shell,
    `su`, `sudo -i`, `chroot`, `at`, `source <(`, `$SHELL`), that command may
    run the body, so its unquoted expansions are real.
    """
    if not _feeds_shell(opener):
        return pending
    return deque(replace(h, inert=False) for h in pending)
