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

    `inert` is set for a quoted delimiter whose body no shell reads. The body
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


# A command that runs its here-document body as shell code: a shell, `ssh`
# (the remote shell runs the body), `eval`, or `source /dev/stdin`. Matched on the
# scrubbed opener line, so a word inside a quoted string does not count.
_SHELL_READER_RE = re.compile(
    r"(?:^|[\s;&|(`=])(?:[^\s;&|()<>`]*/)?(?:bash|sh|zsh|dash|ksh|ash|ssh|eval)(?=[\s;&|)<>`]|$)"
    r"|/dev/stdin"
)


def _feeds_shell(opener: str) -> bool:
    """True when the opener line sends a here-document body to a shell."""
    return _SHELL_READER_RE.search(opener) is not None


def mark_shell_fed(pending: deque[Heredoc], opener: str) -> deque[Heredoc]:
    """Return `pending` with bodies a shell reads no longer inert.

    A quoted delimiter stops the outer shell from expanding the body. When the
    opener line pipes or passes the body to `bash`, `ssh host bash`, or the
    like, that shell runs the body, so its unquoted expansions are real.
    """
    if not _feeds_shell(opener):
        return pending
    return deque(replace(h, inert=False) for h in pending)
