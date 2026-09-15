"""CWE-78 (command injection) detection patterns by language.

Extracted verbatim from ``scan_vulnerabilities.py`` to keep the main scanner
module under the file-size limit (issue #1848). This is a pure data move: the
patterns, descriptions, severities, and recommendations are unchanged. The main
module re-exports ``CWE78_PATTERNS`` so existing callers and tests that read
``scan_vulnerabilities.CWE78_PATTERNS`` continue to work.

CWE-22 (path traversal) detection is NOT here; it is delegated to CodeQL's
``python-security-extended`` query suite. See the ``scan_vulnerabilities`` module
docstring for the buy-vs-build rationale.
"""

import re

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
                "Validate all arguments; avoid string interpolation in "
                "command arguments"
            ),
        },
        {
            "pattern": re.compile(
                r'new\s+Process\s*\(\s*\)\s*\{[^}]*FileName\s*=\s*(\w*(user|input|param|arg|request|cmd)\w*)',
                re.IGNORECASE,
            ),
            "description": "Process with potentially unvalidated FileName",
            "severity": "HIGH",
            "recommendation": "Validate FileName before process creation",
        },
    ],
}
