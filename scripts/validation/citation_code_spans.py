#!/usr/bin/env python3
"""CommonMark backtick-span matching for citation freshness anchors.

Extracted from ``citation_anchors.py`` at the file-size ceiling. The matcher
pairs only equal-length delimiter runs and treats backslash escapes as escapes
only outside a span.
"""

from __future__ import annotations

from collections.abc import Iterator


def _is_escaped(text: str, index: int) -> bool:
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _backtick_run_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


class _BacktickMatch:
    def __init__(
        self, text: str, start: int, end: int, content_start: int, content_end: int
    ) -> None:
        self._text = text
        self._start = start
        self._end = end
        self._content_start = content_start
        self._content_end = content_end

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def span(self) -> tuple[int, int]:
        return (self._start, self._end)

    def group(self, index: int = 0) -> str:
        if index == 0:
            return self._text[self._start : self._end]
        if index == 1:
            return self._text[self._content_start : self._content_end]
        raise IndexError(index)


class _BacktickSpanPattern:
    """CommonMark backtick spans: equal-length runs, escapes only outside."""

    def finditer(self, text: str) -> Iterator[_BacktickMatch]:
        cursor = 0
        while cursor < len(text):
            if text[cursor] != "`" or _is_escaped(text, cursor):
                cursor += 1
                continue
            opening_end = _backtick_run_end(text, cursor)
            length = opening_end - cursor
            scan = opening_end
            close_start = close_end = -1
            while scan < len(text):
                if text[scan] != "`":
                    scan += 1
                    continue
                run_end = _backtick_run_end(text, scan)
                if run_end - scan == length:
                    close_start, close_end = scan, run_end
                    break
                scan = run_end
            if close_start < 0:
                cursor = opening_end
                continue
            yield _BacktickMatch(text, cursor, close_end, opening_end, close_start)
            cursor = close_end

    def findall(self, text: str) -> list[str]:
        return [match.group(1) for match in self.finditer(text)]

    def sub(self, replacement: str, text: str) -> str:
        parts: list[str] = []
        cursor = 0
        for match in self.finditer(text):
            parts.append(text[cursor : match.start()])
            parts.append(replacement)
            cursor = match.end()
        parts.append(text[cursor:])
        return "".join(parts)


_BACKTICK_SPAN = _BacktickSpanPattern()


def _mask_escaped_backticks(text: str) -> str:
    """Blank each backslash-escaped backtick outside a code span, keeping length.

    Outside a span it is a literal, not a delimiter. Inside a span the
    backslash is literal, so the backtick still closes the span.
    """
    if "\\`" not in text:
        return text
    inside = [False] * len(text)
    for match in _BACKTICK_SPAN.finditer(text):
        for index in range(match.start(), match.end()):
            inside[index] = True
    out = list(text)
    for index, char in enumerate(text):
        if char == "`" and not inside[index] and _is_escaped(text, index):
            out[index - 1] = out[index] = " "
    return "".join(out)


def _mask_dquotes_in_backtick_spans(text: str) -> str:
    """Blank double quotes inside backtick spans, keeping length.

    A quote inside a code span is code content, not a prose-quote delimiter.
    Treating it as one pairs it with a later anchor quote and hides that anchor.
    """
    if '"' not in text or "`" not in text:
        return text
    out = list(text)
    for match in _BACKTICK_SPAN.finditer(text):
        for index in range(match.start(), match.end()):
            if out[index] == '"':
                out[index] = " "
    return "".join(out)
