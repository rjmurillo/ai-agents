"""Bash line scrubber for the CWE-78 unquoted-variable check (issue #6294).

Extracted from ``scan_patterns.py`` to keep that module under the file-size
limit. ``scrub_bash_line`` and ``scrub_bash_lines`` hide text that cannot be an
unquoted expansion: comments, quoted spans, and quoted here-document bodies
that only inert readers (cat, tee, python, and the like) consume.
``scan_patterns`` re-exports both names.
"""

import re
from collections import deque
from collections.abc import Sequence

from scan_bash_heredoc import Heredoc, begin_heredoc, is_terminator, mark_shell_fed

# Bash lexer modes. A stack of these tracks quote and substitution nesting.
_MODE_SINGLE = "single"
_MODE_DOUBLE = "double"
_MODE_ANSI = "ansi"
_MODE_SUB = "sub"
_MODE_GROUP = "group"
_MODE_TICK = "tick"
_MODE_ARITH = "arith"
_MODE_CMD_ARITH = "cmdarith"
_MODE_ARITH_GROUP = "arithgroup"
_MODE_CASE = "case"
_MODE_PARAM = "param"
_MODE_DQ_PARAM = "dqparam"


def _blank_run(line: str, i: int, width: int = 1) -> str:
    """Return spaces for the `width` characters at `i`, clipped at end of line."""
    return " " * min(width, len(line) - i)


# Characters after which a word, and so a `#` comment, can begin without whitespace.
# `)` is not here: it ends a word only when it closes a subshell, a `((` command,
# or a case pattern. `_close_paren` and `_step_arith` decide that.
_COMMENT_LEADERS = frozenset(";&|(<>")

# Frames that can host a `case` statement.
_CASE_HOSTS = (_MODE_SUB, _MODE_GROUP, _MODE_CASE)

# Characters that make a following `(` part of a word: `$(`, `name=(`, `<(`, `>(`.
_WORD_PAREN_PREFIXES = "$=<>"


def _is_escaped(line: str, i: int) -> bool:
    """True when the character at `i` is preceded by an odd run of backslashes."""
    count = 0
    while i - count - 1 >= 0 and line[i - count - 1] == "\\":
        count += 1
    return count % 2 == 1


def _starts_word(line: str, i: int) -> bool:
    """True when a shell word can begin at `i`: line start, whitespace, or `;&|(<>` before it."""
    if i == 0 or line[i - 1].isspace():
        return True
    return line[i - 1] in _COMMENT_LEADERS and not _is_escaped(line, i - 1)


def _starts_comment(line: str, i: int) -> bool:
    """A `#` starts a comment at line start, after whitespace, or after `;&|(<>`.

    Bash begins a word after a metacharacter, so `cd /tmp;# note` carries a
    comment. An escaped metacharacter does not end the word. `$#`, `${#x}`, and
    `a#b` stay out of the comment path. A `#` after `)` is decided where the
    `)` closes (`_close_paren`, `_step_arith`): `(cd /tmp)# note` carries a
    comment, but `$(ls)#x` and `$((1))#x` do not, since the `#` joins the word.
    """
    return line[i] == "#" and _starts_word(line, i)


def _step_single(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume one character inside single quotes (everything is literal)."""
    if line[i] == "'":
        stack.pop()
        out.append("'")
    else:
        out.append(" ")
    return i + 1


def _step_ansi(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside `$'...'`: a backslash escapes the next character, even a quote."""
    if line[i] == "\\":
        out.append(_blank_run(line, i, 2))
        return i + 2
    return _step_single(line, i, out, stack)


def _in_double_in_tick_in_double(stack: list[str]) -> bool:
    """True when the top is a DOUBLE opened by `\\"` inside a backtick body in double quotes."""
    return stack[-3:] == [_MODE_DOUBLE, _MODE_TICK, _MODE_DOUBLE]


def _step_double(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside double quotes; text is blanked, `$( )` and backtick bodies are kept.

    `${` pushes `_MODE_DQ_PARAM`: bash nests quotes inside a double-quoted
    `${...}`, so a `'` in there is literal. Inside a backtick body that sits in
    double quotes, bash strips the backslash from `\\"`, so a `\\"` that opened a
    nested double quote here closes it.
    """
    ch = line[i]
    if ch == "\\":
        if line.startswith('"', i + 1) and _in_double_in_tick_in_double(stack):
            stack.pop()
            out.append(' "')
            return i + 2
        out.append(_blank_run(line, i, 2))
        return i + 2
    if ch == '"':
        stack.pop()
        out.append('"')
        return i + 1
    if line.startswith("${", i):
        stack.append(_MODE_DQ_PARAM)
        out.append("  ")
        return i + 2
    if line.startswith("$((", i):
        stack.append(_MODE_ARITH)
        out.append("$((")
        return i + 3
    if line.startswith("$(", i):
        stack.append(_MODE_SUB)
        out.append("$(")
        return i + 2
    if ch == "`":
        stack.append(_MODE_TICK)
        out.append(ch)
        return i + 1
    out.append(" ")
    return i + 1


# Two-character openers that push a mode: `$'...'` and `${...}`.
_DOLLAR_OPENERS = (("$'", _MODE_ANSI), ("${", _MODE_PARAM))


def _open_dollar_form(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Open `$'` or `${` at `i` and return the next index, or 0 when neither starts here."""
    for opener, mode in _DOLLAR_OPENERS:
        if line.startswith(opener, i):
            stack.append(mode)
            out.append(opener)
            return i + len(opener)
    return 0


def _close_paren(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume `)` at `i`. A `#` right after it is a comment only when the word ended.

    The word ends after a bare `(...)` subshell and after a case-pattern `)`. It
    continues after `$(...)`, `name=(...)`, and `<(...)`, so `echo $(date)#$y`
    still expands `$y`. Inside a `_MODE_CASE` frame a `)` ends a pattern and
    closes nothing: the substitution stays open until the `)` after `esac`.
    """
    closed = _MODE_GROUP
    if stack and stack[-1] in (_MODE_SUB, _MODE_GROUP):
        closed = stack.pop()
    out.append(")")
    if closed == _MODE_GROUP and line.startswith("#", i + 1):
        return len(line)
    return i + 1


def _joins_word(line: str, i: int) -> bool:
    """True when the `(` at `i` is part of a word: `$(`, `name=(`, `<(`, or `>(`."""
    return i > 0 and line[i - 1] in _WORD_PAREN_PREFIXES and not _is_escaped(line, i - 1)


def _escape_in_command(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume a backslash pair in shell text; return the next index.

    The pair is an inert escape, except `\\"` in a backtick body that sits in
    double quotes: bash strips the backslash there, so it opens a real nested
    double quote.
    """
    if line.startswith('"', i + 1) and stack[-2:] == [_MODE_DOUBLE, _MODE_TICK]:
        stack.append(_MODE_DOUBLE)
        out.append(' "')
    else:
        out.append(_blank_run(line, i, 2))
    return i + 2


# Text before a word in command position: a separator, bracket, `)`, or list keyword.
_COMMAND_POSITION_RE = re.compile(r"(?:^|[;&|({!)]|(?:^|\s)(?:then|do|else|elif|time))\s*$")


def _keyword_at(line: str, i: int, word: str, closers: str) -> bool:
    """True when keyword `word` stands alone at `i` in command position.

    `echo esac` inside a case body is an argument, not the closer, so `esac`
    needs the same command position as `case`.
    """
    end = i + len(word)
    if not line.startswith(word, i) or not _starts_word(line, i):
        return False
    if not (end == len(line) or line[end].isspace() or line[end] in closers):
        return False
    return _COMMAND_POSITION_RE.search(line[:i]) is not None


def _step_case_keyword(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Open a case frame on `case`, close it on `esac`; 0 when neither is at `i`."""
    top = stack[-1] if stack else ""
    if top == _MODE_CASE and _keyword_at(line, i, "esac", ";&|)"):
        stack.pop()
    elif top in _CASE_HOSTS and _keyword_at(line, i, "case", ""):
        stack.append(_MODE_CASE)
    else:
        return 0
    out.append(line[i : i + 4])
    return i + 4


def _comment_end(line: str, i: int, stack: list[str]) -> int:
    """Return where the comment at `i` ends: end of line, or the closing backtick.

    Bash cuts a backtick body out before parsing it, so a comment inside one
    stops at the closing backtick.
    """
    if stack and stack[-1] == _MODE_TICK:
        for j in range(i, len(line)):
            if line[j] == "`" and not _is_escaped(line, j):
                return j
    return len(line)


def _step_lead(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume an escape, comment, case keyword, or `$'`/`${` opener; 0 when none starts at `i`."""
    ch = line[i]
    if ch == "\\":
        return _escape_in_command(line, i, out, stack)
    if _starts_comment(line, i):
        return _comment_end(line, i, stack)
    if ch in "ce":
        advanced = _step_case_keyword(line, i, out, stack)
        if advanced:
            return advanced
    return _open_dollar_form(line, i, out, stack)


def _step_command(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume one character of unquoted shell text or a substitution body."""
    ch = line[i]
    advanced = _step_lead(line, i, out, stack)
    if advanced:
        return advanced
    if ch == "`":
        if stack and stack[-1] == _MODE_TICK:
            stack.pop()
        else:
            stack.append(_MODE_TICK)
    elif ch == "'":
        stack.append(_MODE_SINGLE)
    elif ch == '"':
        stack.append(_MODE_DOUBLE)
    elif line.startswith("((", i):
        joins_word = i > 0 and line[i - 1] == "$" and not _is_escaped(line, i - 1)
        stack.append(_MODE_ARITH if joins_word else _MODE_CMD_ARITH)
        out.append("((")
        return i + 2
    elif ch == "(":
        stack.append(_MODE_SUB if _joins_word(line, i) else _MODE_GROUP)
    elif ch == ")":
        return _close_paren(line, i, out, stack)
    out.append(ch)
    return i + 1


def _step_arith(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside `((...))` or `$((...))`. Only `))` closes it; else it is shell text.

    A bare `(` opens `_MODE_ARITH_GROUP`, so `<<` in `(( f |= (1 << n) ))` stays a shift.
    A `#` right after the `))` of a `((...))` command is a comment. After the
    `))` of `$((...))` it is part of the word.
    """
    if stack[-1] == _MODE_ARITH_GROUP:
        if line[i] == ")":
            stack.pop()
            out.append(")")
            return i + 1
    elif line.startswith("))", i):
        closed = stack.pop()
        out.append("))")
        if closed == _MODE_CMD_ARITH and line.startswith("#", i + 2):
            return len(line)
        return i + 2
    if line[i] == "(" and not _joins_word(line, i):
        stack.append(_MODE_ARITH_GROUP)
        out.append("(")
        return i + 1
    return _step_command(line, i, out, stack)


def _step_param(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside `${...}`. Only `}` closes it.

    Parentheses and `#` are pattern text here, not substitutions or comments.
    Quotes, backticks, and `$( )` nest as usual.
    """
    ch = line[i]
    if ch == "}":
        stack.pop()
        out.append(ch)
        return i + 1
    if line.startswith("$((", i):
        stack.append(_MODE_ARITH)
        out.append("$((")
        return i + 3
    if line.startswith("$(", i):
        stack.append(_MODE_SUB)
        out.append("$(")
        return i + 2
    if ch in "\\'\"`" or line.startswith(("$'", "${"), i):
        return _step_command(line, i, out, stack)
    out.append(ch)
    return i + 1


def _step_dq_param(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside `${...}` that sits in double quotes. Only `}` closes it.

    The text is quoted, so it is blanked. A `"` opens a nested double quote, and
    a `'` is a literal character. `$( )`, `$(( ))`, backticks, and a nested `${`
    nest as usual.
    """
    ch = line[i]
    if ch == "}":
        stack.pop()
        out.append(" ")
        return i + 1
    if ch == '"':
        stack.append(_MODE_DOUBLE)
        out.append(ch)
        return i + 1
    if ch in "\\`" or line.startswith(("${", "$("), i):
        return _step_double(line, i, out, stack)
    out.append(" ")
    return i + 1


_STEPS = {
    _MODE_SINGLE: _step_single,
    _MODE_ANSI: _step_ansi,
    _MODE_DOUBLE: _step_double,
    _MODE_SUB: _step_command,
    _MODE_GROUP: _step_command,
    _MODE_TICK: _step_command,
    _MODE_ARITH: _step_arith,
    _MODE_CMD_ARITH: _step_arith,
    _MODE_ARITH_GROUP: _step_arith,
    _MODE_CASE: _step_command,
    _MODE_PARAM: _step_param,
    _MODE_DQ_PARAM: _step_dq_param,
}


# Modes whose text runs as shell commands, where a here-document opener is real.
_SHELL_TEXT_MODES = (_MODE_SUB, _MODE_GROUP, _MODE_TICK, _MODE_CASE)


def _lex_line(line: str, stack: list[str], pending: deque[Heredoc]) -> str:
    """Scrub one line, updating the quote `stack` and queueing here-documents.

    Here-document openers are recognised in shell text, at top level or inside
    `$( )` and backticks, so `x=$(cat <<EOF` is seen. A `<<` inside quotes or
    inside arithmetic (`$((1<<n))`) is left alone.
    """
    out: list[str] = []
    i = 0
    while i < len(line):
        if (not stack or stack[-1] in _SHELL_TEXT_MODES) and line.startswith("<<", i):
            i = begin_heredoc(line, i, out, pending)
            continue
        step = _STEPS[stack[-1]] if stack else _step_command
        i = step(line, i, out, stack)
    return "".join(out)


def scrub_bash_line(line: str) -> str:
    """Hide text that cannot be an unquoted expansion from the `$var` regex.

    Drops an unquoted `#` comment, and replaces the interior of single-, double-,
    and `$'...'`-quoted spans with spaces. Quote delimiters stay, so the regex
    lookarounds that skip `"$var"` keep working. `$( )` and backtick bodies, even
    inside double quotes, stay visible because they run as unquoted shell.

    This function sees one line and keeps no state between lines. A line that
    ends with a quote or substitution still open may be opening a multi-line
    string or closing one, and it cannot tell which. It returns the raw line
    then, so code after a closing quote is never hidden. Use `scrub_bash_lines`
    to scrub a whole file with state carried across lines.
    """
    stack: list[str] = []
    text = _lex_line(line, stack, deque())
    return line if stack else text


def _scrub_heredoc_body(line: str, heredoc: Heredoc) -> str:
    """Blank an inert body line (quoted delimiter, inert readers only). Else scrub per line."""
    if heredoc.inert and not is_terminator(line, heredoc):
        body = line.rstrip("\n")
        return " " * len(body) + line[len(body) :]
    return scrub_bash_line(line)


def scrub_bash_lines(lines: Sequence[str]) -> list[str]:
    """Scrub a whole Bash file, carrying quote state across lines.

    Same rules as `scrub_bash_line`, plus two things a single line cannot see.
    The interior of a multi-line quoted string is blanked on every line it
    spans. The body of a here-document with a quoted delimiter (`<<'X'`,
    `<<"X"`, `<<\\X`) is blanked, since the outer shell never expands it. That
    holds only when the body is text. If the opener line sends the body to a
    shell (`bash <<'X'`, `ssh host bash <<'X'`, `<<'X' | sh`, `eval`,
    `source /dev/stdin`), the body is code and is scrubbed one line at a time.
    The body of an unquoted-delimiter here-document is scrubbed one line at a
    time, as before. A reader on a later line (`<<'X' |` then `bash`) is not
    seen, so that body stays blanked.

    It fails open only on unresolved state. If a quote or here-document is still
    open at end of file, every line from where it opened is scrubbed with
    `scrub_bash_line`. A misread quote that a later, unrelated quote closes
    before end of file is not caught by that fallback, so the lexer tracks the
    forms that hide or fake a quote: comments after a metacharacter, bare
    here-document delimiters, `${...}` bodies (nested quotes inside double
    quotes), `\\"` in a backtick body in double quotes, backtick bodies, grouped
    arithmetic (`(1 << n)`), and `case` patterns inside a substitution or group.
    """
    result: list[str] = []
    stack: list[str] = []
    queue: deque[Heredoc] = deque()
    active: Heredoc | None = None
    quote_from: int | None = None
    body_from: int | None = None
    for index, line in enumerate(lines):
        if active is not None:
            result.append(_scrub_heredoc_body(line, active))
            if is_terminator(line, active):
                active = queue.popleft() if queue else None
                if active is None:
                    body_from = None
            continue
        was_open = bool(stack)
        pending: deque[Heredoc] = deque()
        result.append(_lex_line(line, stack, pending))
        pending = mark_shell_fed(pending, result[-1])
        if not stack:
            quote_from = None
        elif not was_open:
            quote_from = index
        if pending:
            queue.extend(pending)
            active = queue.popleft()
            body_from = index + 1 if body_from is None else body_from
    if stack or active is not None:
        marks = [m for m in (quote_from, body_from) if m is not None]
        start = min(marks) if marks else 0
        result[start:] = [scrub_bash_line(line) for line in lines[start:]]
    return result
