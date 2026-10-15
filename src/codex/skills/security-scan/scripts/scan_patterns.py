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

# Bash lexer modes. A stack of these tracks quote and substitution nesting for one line.
_MODE_SINGLE = "single"
_MODE_DOUBLE = "double"
_MODE_ANSI = "ansi"
_MODE_SUB = "sub"
_MODE_TICK = "tick"


def _blank_run(line: str, i: int, width: int = 1) -> str:
    """Return spaces for the `width` characters at `i`, clipped at end of line."""
    return " " * min(width, len(line) - i)


def _starts_comment(line: str, i: int) -> bool:
    """A `#` starts a comment only at line start or after whitespace.

    This keeps `$#`, `${#x}`, and `a#b` out of the comment path.
    """
    return line[i] == "#" and (i == 0 or line[i - 1].isspace())


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


def _step_command(line: str, i: int, out: list[str], stack: list[str]) -> int:
    """Consume one character of unquoted shell text or a substitution body."""
    ch = line[i]
    if ch == "\\":
        out.append(_blank_run(line, i, 2))
        return i + 2
    if _starts_comment(line, i):
        return len(line)
    if line.startswith("$'", i):
        stack.append(_MODE_ANSI)
        out.append("$'")
        return i + 2
    if ch == "`" and stack and stack[-1] == _MODE_TICK:
        stack.pop()
    elif ch == "'":
        stack.append(_MODE_SINGLE)
    elif ch == '"':
        stack.append(_MODE_DOUBLE)
    elif ch == "(":
        stack.append(_MODE_SUB)
    elif ch == ")" and stack and stack[-1] == _MODE_SUB:
        stack.pop()
    out.append(ch)
    return i + 1


_STEPS = {
    _MODE_SINGLE: _step_single,
    _MODE_ANSI: _step_ansi,
    _MODE_DOUBLE: _step_double,
    _MODE_SUB: _step_command,
    _MODE_TICK: _step_command,
}


def scrub_bash_line(line: str) -> str:
    """Hide text that cannot be an unquoted expansion from the `$var` regex.

    Drops an unquoted `#` comment, and replaces the interior of single-, double-,
    and `$'...'`-quoted spans with spaces. Quote delimiters stay, so the regex
    lookarounds that skip `"$var"` keep working. `$( )` and backtick bodies, even
    inside double quotes, stay visible because they run as unquoted shell.

    The scan is per line and keeps no state between lines. A line that ends with
    a quote or substitution still open may be opening a multi-line string or
    closing one, and the lexer cannot tell which. It returns the raw line then,
    so code after a closing quote is never hidden.
    """
    out: list[str] = []
    stack: list[str] = []
    i = 0
    while i < len(line):
        step = _STEPS[stack[-1]] if stack else _step_command
        i = step(line, i, out, stack)
    return line if stack else "".join(out)


# Optional per-pattern line preparation. When a pattern dict has a "scrub" key,
# the scanner runs the regex against ``scrub(line)`` instead of the raw line.
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
            "scrub": scrub_bash_line,
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
