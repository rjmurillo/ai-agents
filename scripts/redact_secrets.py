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
from dataclasses import dataclass

# Ordered: multi-line and specific token shapes first, broad shapes last, so a
# specific match is not pre-empted by the generic hex rule.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
        r".*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
        re.DOTALL)),
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
