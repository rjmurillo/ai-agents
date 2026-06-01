"""Log sanitation helpers for GitHub Core (CWE-117 log forging defense)."""

from __future__ import annotations


def safe_log_str(value: object) -> str:
    """Strip CR/LF from a value before logging it.

    Defends against CWE-117 log forging: GraphQL error messages and other
    remote-sourced text that flow into ``error=%s`` placeholders may contain
    embedded `\\r\\n` sequences that, unsanitized, allow an attacker to
    forge a fake log line. Keeping the substitution in one named helper
    means future log-injection risk is closed at one site, not 12.
    """
    return str(value).replace("\r", "\\r").replace("\n", "\\n")
