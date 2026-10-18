"""CWE-78 (command injection) detection patterns by language.

Extracted from ``scan_vulnerabilities.py`` to keep the main scanner module
under the file-size limit (issue #1848). The patterns, descriptions,
severities, and recommendations are unchanged by the move. The bash
unquoted-variable pattern carries a ``scrub`` hook (issue #6294). The main
module re-exports ``CWE78_PATTERNS`` so existing callers and tests that read
``scan_vulnerabilities.CWE78_PATTERNS`` continue to work.

CWE-22 (path traversal) detection is NOT here; it is delegated to CodeQL's
``python-security-extended`` query suite. See the ``scan_vulnerabilities`` module
docstring for the buy-vs-build rationale.
"""

import re
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

# Bash lexer modes. A stack of these tracks quote and substitution nesting.
_MODE_SINGLE = "single"
_MODE_DOUBLE = "double"
_MODE_ANSI = "ansi"
_MODE_SUB = "sub"
_MODE_GROUP = "group"
_MODE_TICK = "tick"
_MODE_ARITH = "arith"
_MODE_CMD_ARITH = "cmdarith"
_MODE_PARAM = "param"


def _blank_run(line: str, i: int, width: int = 1) -> str:
    """Return spaces for the `width` characters at `i`, clipped at end of line."""
    return " " * min(width, len(line) - i)


# Characters after which a word, and so a `#` comment, can begin without whitespace.
# `)` is not here: it ends a word only when it closes a subshell, a `((` command,
# or a case pattern. `_close_paren` and `_step_arith` decide that.
_COMMENT_LEADERS = frozenset(";&|(<>")

# Characters that make a following `(` part of a word: `$(`, `name=(`, `<(`, `>(`.
_WORD_PAREN_PREFIXES = "$=<>"


def _is_escaped(line: str, i: int) -> bool:
    """True when the character at `i` is preceded by an odd run of backslashes."""
    count = 0
    while i - count - 1 >= 0 and line[i - count - 1] == "\\":
        count += 1
    return count % 2 == 1


def _starts_comment(line: str, i: int) -> bool:
    """A `#` starts a comment at line start, after whitespace, or after `;&|(<>`.

    Bash begins a word after a metacharacter, so `cd /tmp;# note` carries a
    comment. An escaped metacharacter does not end the word. `$#`, `${#x}`, and
    `a#b` stay out of the comment path. A `#` after `)` is decided where the
    `)` closes (`_close_paren`, `_step_arith`): `(cd /tmp)# note` carries a
    comment, but `$(ls)#x` and `$((1))#x` do not, since the `#` joins the word.
    """
    if line[i] != "#":
        return False
    if i == 0 or line[i - 1].isspace():
        return True
    return line[i - 1] in _COMMENT_LEADERS and not _is_escaped(line, i - 1)


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


def _step_double(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside double quotes; text is blanked, `$( )` and backtick bodies are kept."""
    ch = line[i]
    if ch == "\\":
        out.append(_blank_run(line, i, 2))
        return i + 2
    if ch == '"':
        stack.pop()
        out.append('"')
        return i + 1
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

    The word ends after a bare `(...)` subshell and after a `)` with no opener on
    the stack (a case pattern). It continues after `$(...)`, `name=(...)`, and
    `<(...)`, so `echo $(date)#$y` still expands `$y`.
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


def _step_command(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume one character of unquoted shell text or a substitution body."""
    ch = line[i]
    if ch == "\\":
        out.append(_blank_run(line, i, 2))
        return i + 2
    if _starts_comment(line, i):
        return len(line)
    opened = _open_dollar_form(line, i, out, stack)
    if opened:
        return opened
    if ch == "`" and stack and stack[-1] == _MODE_TICK:
        stack.pop()
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

    A `#` right after the `))` of a `((...))` command is a comment. After the
    `))` of `$((...))` it is part of the word.
    """
    if line.startswith("))", i):
        closed = stack.pop()
        out.append("))")
        if closed == _MODE_CMD_ARITH and line.startswith("#", i + 2):
            return len(line)
        return i + 2
    return _step_command(line, i, out, stack)


def _step_param(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume inside `${...}`. Only `}` closes it.

    Parentheses and `#` are pattern text here, not substitutions or comments.
    Quotes and `$( )` nest as usual.
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
    if ch in "\\'\"" or line.startswith(("$'", "${"), i):
        return _step_command(line, i, out, stack)
    out.append(ch)
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
    _MODE_PARAM: _step_param,
}


# Modes whose text runs as shell commands, where a here-document opener is real.
_SHELL_TEXT_MODES = (_MODE_SUB, _MODE_GROUP, _MODE_TICK)

# A here-document opener: `<<`, optional `-`, then the delimiter word. Groups
# 2 to 4 are the quoted forms ('X', "X", \X); group 5 is a bare word.
# A bare word is any run of non-metacharacters, so `<<!`, `<<1`, and `1<<2` are
# openers, as in bash. Arithmetic shifts are screened out by the lexer mode.
_HEREDOC_RE = re.compile(
    r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\([^\s;|&<>()'\"\\$`]+)"
    r"|([^\s;|&<>()'\"\\$`]+))"
)


@dataclass(frozen=True, slots=True)
class _Heredoc:
    """One pending here-document: where its body ends and whether it expands."""

    delimiter: str
    strip_tabs: bool
    quoted: bool


def _begin_heredoc(line: str, i: int, out: list[str], pending: deque[_Heredoc]) -> int:
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
        pending.append(_Heredoc(word, dash == "-", quoted))
    out.append("<<")
    return i + 2


def _lex_line(line: str, stack: list[str], pending: deque[_Heredoc]) -> str:
    """Scrub one line, updating the quote `stack` and queueing here-documents.

    Here-document openers are recognised in shell text, at top level or inside
    `$( )` and backticks, so `x=$(cat <<EOF` is seen. A `<<` inside quotes or
    inside arithmetic (`$((1<<n))`) is left alone.
    """
    out: list[str] = []
    i = 0
    while i < len(line):
        if (not stack or stack[-1] in _SHELL_TEXT_MODES) and line.startswith("<<", i):
            i = _begin_heredoc(line, i, out, pending)
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


def _is_terminator(line: str, heredoc: _Heredoc) -> bool:
    """A body ends at a line equal to the delimiter. Trailing blanks do not match."""
    text = line.rstrip("\n")
    if heredoc.strip_tabs:
        text = text.lstrip("\t")
    return text == heredoc.delimiter


def _scrub_heredoc_body(line: str, heredoc: _Heredoc) -> str:
    """Blank a quoted-delimiter body line, which never expands. Else scrub per line."""
    if heredoc.quoted and not _is_terminator(line, heredoc):
        body = line.rstrip("\n")
        return " " * len(body) + line[len(body) :]
    return scrub_bash_line(line)


def scrub_bash_lines(lines: Sequence[str]) -> list[str]:
    """Scrub a whole Bash file, carrying quote state across lines.

    Same rules as `scrub_bash_line`, plus two things a single line cannot see.
    The interior of a multi-line quoted string is blanked on every line it
    spans. The body of a here-document with a quoted delimiter (`<<'X'`,
    `<<"X"`, `<<\\X`) is blanked, since it never expands. The body of an
    unquoted-delimiter here-document is scrubbed one line at a time, as before.

    It fails open only on unresolved state. If a quote or here-document is still
    open at end of file, every line from where it opened is scrubbed with
    `scrub_bash_line`. A misread quote that a later, unrelated quote closes
    before end of file is not caught by this fallback. The lexer therefore
    tracks the shell forms that hide or fake a quote: comments after a
    metacharacter, bare here-document delimiters, and `${...}` bodies.
    """
    result: list[str] = []
    stack: list[str] = []
    queue: deque[_Heredoc] = deque()
    active: _Heredoc | None = None
    quote_from: int | None = None
    body_from: int | None = None
    for index, line in enumerate(lines):
        if active is not None:
            result.append(_scrub_heredoc_body(line, active))
            if _is_terminator(line, active):
                active = queue.popleft() if queue else None
                if active is None:
                    body_from = None
            continue
        was_open = bool(stack)
        pending: deque[_Heredoc] = deque()
        result.append(_lex_line(line, stack, pending))
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


# Optional per-pattern file preparation. When a pattern dict has a "scrub_lines"
# key, the scanner runs the regex against ``scrub_lines(lines)[n]`` instead of
# raw line ``n``, so the hook can carry state from one line to the next.
# CWE-78: Command Injection patterns by language
CWE78_PATTERNS = {
    "python": [
        {
            "pattern": re.compile(
                r'subprocess\.(run|call|Popen|check_output|check_call)\s*\(\s*f["\']',
            ),
            "description": "Subprocess with f-string command (potential injection)",
            "severity": "CRITICAL",
            "recommendation": "Use list form of command arguments instead of shell string",
        },
        {
            "pattern": re.compile(
                r"subprocess\.(run|call|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True",
            ),
            "description": "Subprocess with shell=True",
            "severity": "HIGH",
            "recommendation": "Avoid shell=True; use list form of command arguments",
        },
        {
            "pattern": re.compile(
                r'subprocess\.(run|call|Popen|check_output|check_call)\s*\(\s*["\'][^"\']*\s*\+',
            ),
            "description": "Subprocess with string concatenation",
            "severity": "CRITICAL",
            "recommendation": "Use list form of command arguments instead of string concatenation",
        },
        {
            "pattern": re.compile(
                r"eval\s*\(\s*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "eval() with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use eval() with user input",
        },
        {
            "pattern": re.compile(
                r"exec\s*\(\s*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "exec() with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use exec() with user input",
        },
    ],
    "powershell": [
        {
            "pattern": re.compile(
                r'Invoke-Expression\s+["\'][^"\']*\$(\w+)',
            ),
            "description": "Invoke-Expression with variable interpolation",
            "severity": "CRITICAL",
            "recommendation": (
                "Avoid Invoke-Expression; use direct cmdlet calls or & "
                "operator with validated arguments"
            ),
        },
        {
            "pattern": re.compile(
                r"Invoke-Expression\s+\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Invoke-Expression with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use Invoke-Expression with user input",
        },
        {
            "pattern": re.compile(
                r"&\s+\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Call operator with potentially unvalidated command",
            "severity": "HIGH",
            "recommendation": "Validate command before execution",
        },
        {
            "pattern": re.compile(
                r"Start-Process\s+[^-]*-ArgumentList\s+[^|]*\$(\w*(user|input|param|arg|request)\w*)",
                re.IGNORECASE,
            ),
            "description": "Start-Process with potentially unvalidated arguments",
            "severity": "HIGH",
            "recommendation": "Validate all arguments before passing to Start-Process",
        },
    ],
    "bash": [
        {
            "pattern": re.compile(
                r"eval\s+[\"']?\$",
            ),
            "description": "eval with variable expansion",
            "severity": "CRITICAL",
            "recommendation": "Avoid eval; use direct command execution with proper quoting",
        },
        {
            "pattern": re.compile(
                r"\$\(\s*\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Command substitution with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Validate input before command substitution",
        },
        {
            "pattern": re.compile(
                r"`\s*\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Backtick command substitution with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Validate input before command substitution; prefer $() syntax",
        },
        {
            "pattern": re.compile(
                r"(?<![\"'])\$\w+(?![\"'\w])",
            ),
            "scrub_lines": scrub_bash_lines,
            "description": "Unquoted variable expansion (potential word splitting/injection)",
            "severity": "MEDIUM",
            "recommendation": 'Quote all variable expansions: use "$var" instead of $var',
        },
    ],
    "csharp": [
        {
            "pattern": re.compile(
                r"Process\.Start\s*\([^)]*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Process.Start with potentially unvalidated command",
            "severity": "HIGH",
            "recommendation": "Validate command and arguments before execution",
        },
        {
            "pattern": re.compile(
                r'ProcessStartInfo\s*\{[^}]*Arguments\s*=\s*\$"',
            ),
            "description": "ProcessStartInfo with interpolated arguments",
            "severity": "HIGH",
            "recommendation": (
                "Validate all arguments; avoid string interpolation in command arguments"
            ),
        },
        {
            "pattern": re.compile(
                r"new\s+Process\s*\(\s*\)\s*\{[^}]*FileName\s*=\s*(\w*(user|input|param|arg|request|cmd)\w*)",
                re.IGNORECASE,
            ),
            "description": "Process with potentially unvalidated FileName",
            "severity": "HIGH",
            "recommendation": "Validate FileName before process creation",
        },
    ],
}
