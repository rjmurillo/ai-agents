#!/usr/bin/env python3
"""Security review script for memory export files.

Scans exported memory JSON files for sensitive information patterns including
API keys, tokens, passwords, secrets, private file paths, database connection
strings, email addresses, and PII patterns.

EXIT CODES:
  0  - Success: No sensitive data patterns detected
  1  - Error: Sensitive data patterns found or pattern scanning failed

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_GENERIC_SECRET_PATTERN = (
    r"(?<![a-zA-Z0-9~_.-])[a-zA-Z0-9~_.-]{34,}(?![a-zA-Z0-9~_.-])"
)
_FORGETFUL_ID_UUID = re.compile(
    r'(?<!\\)"(?:id|user_id)"\s*:\s*'
    r'"(?P<uuid>[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})"'
)
_CANONICAL_UUID = re.compile(
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
)

SENSITIVE_PATTERNS: dict[str, list[str]] = {
    "API Keys/Tokens": [
        r"api[_-]?key",
        r"access[_-]?token",
        r"bearer\s+[a-zA-Z0-9_-]{20,}",
        r"github[_-]?token",
        r"gh[ps]_[a-zA-Z0-9]{36}",
        r"AKIA[0-9A-Z]{16}",
        r"xox[baprs]-[0-9a-zA-Z]{10,}",
        r"npm_[A-Za-z0-9]{36}",
    ],
    "Passwords/Secrets": [
        r"password\s*[:=]\s*[\"']?[^\"\s]{8,}",
        r"secret\s*[:=]",
        r"credential",
        r"auth[_-]?key",
        _GENERIC_SECRET_PATTERN,
        r"[A-Za-z0-9+/=]{40,}",
    ],
    "Private Keys": [
        r"BEGIN\s+(RSA|PRIVATE|ENCRYPTED)\s+KEY",
        r"private[_-]?key",
        r"SHA256:[A-Za-z0-9+/=]{43}",
    ],
    "File Paths": [
        r"/home/[a-zA-Z0-9_-]+/",
        r"C:\\Users\\[^\\]+\\",
        r"/Users/[^/]+/",
    ],
    "Database Credentials": [
        r"connection[_-]?string",
        r"jdbc:",
        r"mongodb://",
        r"postgres://",
        r"mysql://",
    ],
    "Email/PII": [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        r"ssn\s*[:=]",
        r"social[_-]?security",
        r"(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.\d+\.\d+",
    ],
}


def _is_forgetful_id_uuid(line: str, match: re.Match[str]) -> bool:
    if _CANONICAL_UUID.fullmatch(match.group()) is None:
        return False
    return any(
        id_match.span("uuid") == match.span()
        for id_match in _FORGETFUL_ID_UUID.finditer(line)
    )


def _line_has_sensitive_match(
    line: str,
    pattern: str,
    compiled: re.Pattern[str],
) -> bool:
    matches = compiled.finditer(line)
    if pattern != _GENERIC_SECRET_PATTERN:
        return next(matches, None) is not None
    return any(not _is_forgetful_id_uuid(line, match) for match in matches)


def scan_file(export_file: Path, quiet: bool = False) -> int:
    if not quiet:
        print(f"Scanning export file for sensitive data: {export_file}")
        print()

    content = export_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    found_issues: list[dict[str, str | int]] = []
    total_matches = 0

    for category, patterns in SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                match_lines: list[int] = []
                for i, line in enumerate(lines, 1):
                    if _line_has_sensitive_match(line, pattern, compiled):
                        match_lines.append(i)
                if match_lines:
                    total_matches += len(match_lines)
                    found_issues.append({
                        "category": category,
                        "pattern": pattern,
                        "count": len(match_lines),
                        "lines": ", ".join(str(n) for n in match_lines[:3]),
                    })
            except re.error as e:
                found_issues.append({
                    "category": f"{category} (SCAN FAILED)",
                    "pattern": pattern,
                    "count": 1,
                    "lines": f"Error: {e}",
                })

    if not found_issues:
        if not quiet:
            print("CLEAN - No sensitive data patterns detected")
            print()
            print("Export file is safe to commit to version control.")
        return 0

    if not quiet:
        print("WARNING - Sensitive data patterns detected!")
        print()
        print(f"Found {total_matches} potential sensitive data matches:")
        print()
        print(f"{'Category':<30} {'Pattern':<40} {'Matches':<10} {'Sample Lines'}")
        print("-" * 100)
        for issue in found_issues:
            cat = issue['category']
            pat = issue['pattern']
            cnt = issue['count']
            sample = issue['lines']
            print(f"{cat:<30} {pat:<40} {cnt:<10} {sample}")
        print()
        print("ACTION REQUIRED:")
        print(f"1. Review the export file manually at: {export_file}")
        print("2. Remove or redact sensitive data")
        print("3. Re-run this script to verify clean")
        print("4. DO NOT commit until scan is clean")
        print()
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Security review for memory export files")
    parser.add_argument("export_file", type=Path, help="Path to exported memory JSON file")
    parser.add_argument("--quiet", action="store_true", help="Suppress output, only set exit code")
    args = parser.parse_args(argv)

    if not args.export_file.is_file():
        print(f"ERROR: File not found: {args.export_file}", file=sys.stderr)
        return 1

    return scan_file(args.export_file, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
