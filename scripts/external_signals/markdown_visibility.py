"""Find the text of a Markdown body that GitHub shows, line by line.

Fenced code and HTML comments are blanked in one pass, keeping the line count,
so callers can align visible and raw lines by index. Inline code spans keep a
``<!--`` literal, and a backslash-escaped backtick opens no span. The scan is
line based and cannot match every case GitHub renders, so it also reports a
comment or fence left open at the end. Standard library only: the spec
coverage check runs it under a bare ``python3`` (issue #6182).
"""

from __future__ import annotations

import re

_TICKS = re.compile(r"`+")
_FENCE = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,})(?P<info>.*)$")


def _closes_fence(line: str, opener: str) -> bool:
    """True when ``line`` is a bare run of the opener's character, as long or longer."""

    match = _FENCE.match(line)
    return (
        match is not None
        and match.group("run")[0] == opener[0]
        and len(match.group("run")) >= len(opener)
        and not match.group("info").strip()
    )


def _code_span_end(text: str, tick: int) -> int:
    """Return where the backtick run at ``tick`` stops hiding ``<!--``.

    A run of N backticks opens a code span that closes at the next run of
    exactly N. Text inside the span is literal. An unmatched run is literal
    backticks, so only the run itself is skipped.
    """

    run = _TICKS.match(text, tick)
    assert run is not None  # caller passes the index of a backtick
    for closer in _TICKS.finditer(text, run.end()):
        if len(closer.group()) == len(run.group()):
            return closer.end()
    return run.end()


def _unescaped_tick(text: str, stop: int) -> int:
    """Index of the first backtick before ``stop`` not escaped by a backslash, or -1."""

    for match in _TICKS.finditer(text, 0, stop):
        slashes = len(text[: match.start()]) - len(text[: match.start()].rstrip("\\"))
        if slashes % 2 == 0:
            return match.start()
    return -1


def _strip_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Drop ``<!-- -->`` spans from one line, carrying an open comment across lines.

    ``<!--`` inside an inline code span is literal text, as GitHub renders it.
    """

    kept: list[str] = []
    rest = line
    while rest:
        if in_comment:
            end = rest.find("-->")
            if end < 0:
                return "".join(kept), True
            rest, in_comment = rest[end + 3 :], False
            continue
        start = rest.find("<!--")
        if start < 0:
            kept.append(rest)
            break
        tick = _unescaped_tick(rest, start)
        if tick >= 0:
            skip = _code_span_end(rest, tick)
            kept.append(rest[:skip])
            rest = rest[skip:]
            continue
        kept.append(rest[:start])
        # Search for --> from the second dash, so <!--> and <!---> close at once.
        rest, in_comment = rest[start + 2 :], True
    return "".join(kept), in_comment


def scan_hidden(body: str) -> tuple[str, str | None]:
    """Blank fenced code and HTML comments in one pass, keeping the line count.

    Whichever construct opens first wins, as Markdown renders it: ``<!--``
    inside a fence is literal text, and a fence line inside a comment is hidden.
    A closing fence is a bare run (```python opens, never closes). Returns the
    visible text and ``"comment"`` or ``"fence"`` when one is still open at the
    end, which ``unclosed_construct`` reports so callers can fail closed.
    """

    out: list[str] = []
    fence = ""
    in_comment = False
    for line in body.split("\n"):
        if fence:
            if _closes_fence(line, fence):
                fence = ""
            out.append("")
            continue
        match = None if in_comment else _fence_opener(line)
        if match:
            fence = match.group("run")
            out.append("")
            continue
        visible, in_comment = _strip_comments(line, in_comment)
        out.append(visible)
    unclosed = "fence" if fence else "comment" if in_comment else None
    return "\n".join(out), unclosed


def _fence_opener(line: str) -> re.Match[str] | None:
    """Match a fence opener. A backtick fence's info string may not hold a backtick."""

    match = _FENCE.match(line)
    if match and match.group("run")[0] == "`" and "`" in match.group("info"):
        return None
    return match


def unclosed_construct(body: str) -> str | None:
    """Return ``"comment"`` or ``"fence"`` when one is never closed, else None.

    An unclosed construct hides the rest of the body, and a line-based scan
    cannot tell every such case from what GitHub renders. Callers that gate on
    the checkboxes fail closed on it rather than trust what stays visible.
    """

    return scan_hidden(body)[1]
