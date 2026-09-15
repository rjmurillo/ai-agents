"""Domain classification for GitHub PR/review comments.

Shared, single-source-of-truth for the keyword-based triage that sorts a
comment body into one of five domains (security, bug, style, summary,
general). Previously this logic (the compiled patterns plus ``classify_domain``)
was duplicated verbatim in ``get_pr_review_comments.py`` and
``get_unaddressed_comments.py`` (Issue #2816, finding 4).

NOTE: Plugin-distributed copy at .claude/lib/github_core/ and
src/copilot-cli/lib/github_core/. Run ``python3 scripts/sync_plugin_lib.py``
(and the build) to sync changes.
"""

from __future__ import annotations

import re

_SECURITY_PATTERN = re.compile(
    r"cwe-\d+|vulnerability|vulnerabilities|injection|xss|sql|csrf"
    r"|\bauth(?:entication|orization|enticat|orized)?\b"
    r"|secrets?|credentials?|toctou|symlink|traversal|sanitiz"
    r"|\bescap(?:e|ing)\b",
    re.IGNORECASE,
)
_BUG_PATTERN = re.compile(
    r"throws?\s+error|error\s+(?:occurs?|occurred|happens?|when|while)"
    r"|\bcrash(?:es|ed|ing)?\b|\bexception(?:s)?\b|\bfail(?:ed|s|ure|ing)\b"
    r"|null\s+(?:pointer|reference|ref)\b|undefined\s+(?:behavior|reference|variable)\b"
    r"|race\s+condition|deadlock|memory\s+leak",
    re.IGNORECASE,
)
_STYLE_PATTERN = re.compile(
    r"formatting|naming|indentation|whitespace|convention|code\s*style"
    r"|stylistic|readability|cleanup|refactor|refactoring",
    re.IGNORECASE,
)
_SUMMARY_PATTERN = re.compile(
    r"(?m)^\s*#{1,3}\s*(?:summary|overview|changes|walkthrough)",
    re.IGNORECASE,
)


def classify_domain(body: str) -> str:
    """Classify a comment into a domain based on keyword matching.

    Non-string input (for example a JSON ``null`` body surfaced as ``None``)
    is treated as unclassifiable and returns ``"general"``.
    """
    if not isinstance(body, str) or not body.strip():
        return "general"
    if _SECURITY_PATTERN.search(body):
        return "security"
    if _BUG_PATTERN.search(body):
        return "bug"
    if _STYLE_PATTERN.search(body):
        return "style"
    if _SUMMARY_PATTERN.search(body):
        return "summary"
    return "general"
