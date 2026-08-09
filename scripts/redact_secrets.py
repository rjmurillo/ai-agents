#!/usr/bin/env python3
"""Redact secret/PII token shapes from free-text before it is emitted.

Issue #1975 / REQ-008 Sec F4 (CWE-209 information disclosure, CWE-532 sensitive
data in logs): halt-block `answer`/`evidence` fields and other free-text the
agent writes can carry a credential, token, or PII verbatim, and those fields
flow into PR descriptions, session logs, and tally files that land in git.

This is an in-process redactor for that free-text, NOT a repository secret
scanner (use CodeQL / gitleaks-class tooling for scanning committed code). It
replaces matched token shapes with `[redacted: <reason>]`.

Scope/caveat: apply to UNTRUSTED free-text (a proposer's Q3/Q4 answers, halt-
block evidence), not to structured fields that legitimately hold hex. The
`hex-secret` rule (>= 32 hex chars) matches a 40-char commit SHA or a 64-char
content hash, so do not run the default profile over a field whose contract is
"a git SHA"; pass include_hex=False there.

Exit codes (ADR-035): 0 = success (redactions may or may not have occurred),
2 = usage error.

Usage:
    redact_secrets.py [FILE]          # FILE or stdin -> redacted text on stdout
    echo "Bearer abc..." | redact_secrets.py
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass

# Ordered: multi-line and specific token shapes first, broad shapes last, so a
# specific match is not pre-empted by the generic hex rule.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
            r".*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
            re.DOTALL,
        ),
    ),
    ("github-token", re.compile(r"\b(?:ghp|ghs|gho|ghu|ghr)_[A-Za-z0-9]{36,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=~]{8,}", re.IGNORECASE)),
    # Unicode-aware local part and single-label domains (e.g. Alice@corp) are
    # matched: the TLD suffix is optional. This over-redacts handle-like shapes
    # such as foo@bar, which is the safe failure mode for untrusted free-text.
    ("email", re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*", re.UNICODE)),
    # A 32+ hex run anywhere, even immediately after a word char like `_`; the
    # lookarounds bound the run by hex chars rather than \b word boundaries.
    ("hex-secret", re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")),
]

_PLACEHOLDER = "[redacted: {reason}]"


def _json_key_word(word: str) -> str:
    """Match a credential-key word in literal or JSON Unicode-escaped form."""
    characters: list[str] = []
    for character in word:
        escaped_forms = {rf"\\u{ord(character):04x}"}
        if character.isalpha():
            escaped_forms.add(rf"\\u{ord(character.upper()):04x}")
        characters.append(rf"(?:{re.escape(character)}|{'|'.join(sorted(escaped_forms))})")
    return "".join(characters)


_CREDENTIAL_SEPARATOR_CHARACTER = rf"(?:[-_\s]|{_json_key_word('-')}|{_json_key_word('_')}|\\u0020)"
_CREDENTIAL_SEPARATOR = rf"{_CREDENTIAL_SEPARATOR_CHARACTER}?"
_CREDENTIAL_NAMESPACE_CHARACTER = r"(?:[A-Za-z0-9]|\\u[0-9a-f]{4})"
_CREDENTIAL_NAMESPACE = rf"(?:{_CREDENTIAL_NAMESPACE_CHARACTER}|{_CREDENTIAL_SEPARATOR_CHARACTER})*"
_CREDENTIAL_KEY_BASE = (
    "(?:"
    + "|".join(
        (
            _json_key_word("api") + _CREDENTIAL_SEPARATOR + _json_key_word("key"),
            _json_key_word("access") + _CREDENTIAL_SEPARATOR + _json_key_word("key"),
            _json_key_word("private") + _CREDENTIAL_SEPARATOR + _json_key_word("key"),
            _json_key_word("client") + _CREDENTIAL_SEPARATOR + _json_key_word("secret"),
            _json_key_word("access") + _CREDENTIAL_SEPARATOR + _json_key_word("token"),
            _json_key_word("refresh") + _CREDENTIAL_SEPARATOR + _json_key_word("token"),
            _json_key_word("password"),
            _json_key_word("passwd"),
            _json_key_word("secret"),
            _json_key_word("token"),
        )
    )
    + ")"
)
_CREDENTIAL_KEY = _CREDENTIAL_NAMESPACE + _CREDENTIAL_KEY_BASE
_CREDENTIAL_KEY_QUOTE = r"(?:\\?[\"'])?"
_CREDENTIAL_PREFIX = (
    rf"(?<![\w-]){_CREDENTIAL_KEY_QUOTE}{_CREDENTIAL_KEY}"
    rf"{_CREDENTIAL_KEY_QUOTE}\s*[:=]\s*"
)
_CREDENTIAL_ASSIGNMENT = re.compile(rf"(?i)({_CREDENTIAL_PREFIX})")


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Redacted text plus the reasons that fired (in order, with duplicates)."""

    text: str
    reasons: tuple[str, ...]

    @property
    def redacted(self) -> bool:
        return bool(self.reasons)


def redact(text: str, *, include_hex: bool = True) -> RedactionResult:
    """Return ``text`` with secret/PII token shapes replaced by placeholders.

    ``include_hex=False`` skips the broad ``hex-secret`` rule, for fields whose
    contract is a git SHA or other legitimate long-hex value.
    """
    reasons: list[str] = []
    out = text
    for reason, pattern in _RULES:
        if reason == "hex-secret" and not include_hex:
            continue

        def _sub(match: re.Match[str], _reason: str = reason) -> str:
            reasons.append(_reason)
            return _PLACEHOLDER.format(reason=_reason)

        out = pattern.sub(_sub, out)
    return RedactionResult(text=out, reasons=tuple(reasons))


def redact_ci_sink(text: str, *, secret_values: Iterable[str] = ()) -> RedactionResult:
    """Redact CI credentials using exact values, wrappers, and token shapes."""
    reasons: list[str] = []
    out = text
    for secret in secret_values:
        if len(secret) >= 8 and secret in out:
            out = out.replace(secret, "***")
            reasons.append("environment-secret")

    out, authorization_count = re.subn(
        r"(?i)(authorization:\s*(?:bearer|token|basic)\s+)\S+",
        r"\1***",
        out,
    )
    reasons.extend(["authorization-header"] * authorization_count)
    out, url_count = re.subn(
        r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^@\s]+@",
        r"\1******@",
        out,
    )
    reasons.extend(["url-credential"] * url_count)
    shaped = redact(out, include_hex=False)
    out = shaped.text
    reasons.extend(shaped.reasons)

    def _is_value_boundary(position: int) -> bool:
        if position >= len(out):
            return True
        return out[position].isspace() or out[position] in ",;}]"

    def _line_end(position: int) -> int:
        newline_positions = [
            candidate
            for candidate in (out.find("\n", position), out.find("\r", position))
            if candidate >= 0
        ]
        return min(newline_positions) if newline_positions else len(out)

    def _preceding_backslash_count(position: int) -> int:
        count = 0
        cursor = position - 1
        while cursor >= 0 and out[cursor] == "\\":
            count += 1
            cursor -= 1
        return count

    def _quoted_value_end(start: int, quote: str) -> int:
        position = start + len(quote)
        while position < len(out):
            closing = out.find(quote, position)
            if closing < 0:
                return _line_end(start)
            if len(quote) == 1 and _preceding_backslash_count(closing) % 2:
                position = closing + len(quote)
                continue
            tail_start = closing + len(quote)
            if _is_value_boundary(tail_start):
                return tail_start
            position = tail_start
        return len(out)

    def _value_end(start: int) -> int:
        if out.startswith("[redacted:", start):
            closing = out.find("]", start)
            if closing >= 0:
                return closing + 1
        for quote in ('\\"', "\\'", '"', "'"):
            if out.startswith(quote, start):
                return _quoted_value_end(start, quote)
        position = start
        while not _is_value_boundary(position):
            position += 1
        return position

    def _redacted_assignment(prefix: str, value: str) -> str | None:
        stripped = value.strip()
        if not stripped or re.fullmatch(r"\[redacted: [^\]]+\]", stripped):
            return None
        leading_length = len(value) - len(value.lstrip())
        leading = value[:leading_length]
        scalar = value[leading_length:]
        quote = ""
        if scalar.startswith(('\\"', "\\'")):
            quote = scalar[:2]
        elif scalar.startswith(('"', "'")):
            quote = scalar[:1]
        if quote:
            closing = scalar.endswith(quote) and len(scalar) > len(quote)
            return f"{prefix}{leading}{quote}***{quote if closing else ''}"
        return f"{prefix}{leading}***"

    redacted_parts: list[str] = []
    cursor = 0
    assignment_count = 0
    while True:
        match = _CREDENTIAL_ASSIGNMENT.search(out, cursor)
        if match is None:
            redacted_parts.append(out[cursor:])
            break
        value_start = match.end()
        value_end = _value_end(value_start)
        replacement = _redacted_assignment(match.group(1), out[value_start:value_end])
        redacted_parts.append(out[cursor:match.start()])
        if replacement is None:
            redacted_parts.append(out[match.start():value_end])
        else:
            redacted_parts.append(replacement)
            assignment_count += 1
        cursor = value_end

    out = "".join(redacted_parts)
    reasons.extend(["credential-assignment"] * assignment_count)

    return RedactionResult(
        text=out,
        reasons=tuple(reasons),
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("usage: redact_secrets.py [FILE]", file=sys.stderr)
        return 2
    try:
        text = open(args[0], encoding="utf-8").read() if args else sys.stdin.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"redact_secrets: cannot read input: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(redact(text).text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
