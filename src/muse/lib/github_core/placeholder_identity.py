"""Centralized placeholder identity denylist for pr-autofix worktrees.

WHY THIS MODULE EXISTS
----------------------
Squash merge a2cc80e7 (#2458) on main carried a spurious
``Co-authored-by: Test <test@test.com>`` trailer. The bad identity came
from a pytest fixture that called ``git config user.email test@test.com``
with the wrong cwd, writing the placeholder into a pr-autofix worktree's
local ``.git/config``. GitHub then assembled the squash trailer block from
every commit author in the PR's history.

Two confirmed leak sources (issue #2466):
- tests/skills/adr-review/test_detect_adr_changes.py:117-127
- tests/skills/metrics/test_collect_metrics.py:133-143

This module is the SINGLE SOURCE OF TRUTH for:
- Which (name, email) pairs are placeholder identities.
- How to detect them.
- How to strip them from a squash-commit body.

All three defenses (worktree bootstrap, pre-push guard, squash sanitizer)
import from here. Do NOT duplicate the denylist elsewhere.

INTENTIONAL EXCLUSION: RFC-2606 reserved addresses (*@example.com,
*@example.org, *@example.net) are NOT on the denylist. Approximately ten
test files in this repo use those addresses as legitimate fixture
identities. Only the specific ``test@test.com`` leak pattern is blocked.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Denylist constants
# ---------------------------------------------------------------------------

# Exact email addresses that are never legitimate commit identities.
# Cite: issue #2466, commit a2cc80e7, PR #2458.
PLACEHOLDER_EMAILS: frozenset[str] = frozenset({"test@test.com"})

# Case-insensitive regex patterns for placeholder emails.
PLACEHOLDER_EMAIL_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test@test\.com$", re.IGNORECASE),
)

# Bare names that are placeholder-like ONLY when the email is also on the
# denylist. The name "Test" alone is not blocked because it can appear as
# a legitimate partial name in real addresses like test@example.com.
PLACEHOLDER_NAMES: frozenset[str] = frozenset({"test"})

# Regex matching a Co-authored-by trailer line (case-insensitive per git spec).
_CO_AUTHOR_RE = re.compile(
    r"^Co-authored-by:\s+([^<]*)<([^>]+)>\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_placeholder_identity(name: str, email: str) -> bool:
    """Return True when (name, email) matches the placeholder denylist.

    The check is case-insensitive on both fields. Only identities that
    are BOTH on the name list AND the email list (or match an email regex)
    are blocked. A bare name of "Test" with email "test@example.com" is
    NOT blocked (the example.com domain is legitimate per RFC 2606).

    Args:
        name:  git author/committer name.
        email: git author/committer email.

    Returns:
        True when the identity is a known placeholder; False otherwise.
    """
    email_lower = email.lower().strip()
    name_lower = name.lower().strip()

    if email_lower in {e.lower() for e in PLACEHOLDER_EMAILS}:
        return True
    for pattern in PLACEHOLDER_EMAIL_REGEXES:
        if pattern.match(email_lower):
            return True
    # Belt-and-suspenders: bare name "test" with ANY .test TLD
    if name_lower in {n.lower() for n in PLACEHOLDER_NAMES}:
        if re.search(r"@[^@]+\.test$", email_lower):
            return True
    return False


def filter_coauthor_trailers(body: str) -> str:
    """Strip Co-authored-by trailers whose email matches the placeholder denylist.

    Preserves all other trailers (Copilot, rjmurillo-bot, real users).
    The match is performed line-by-line so only the offending trailer is
    removed; the rest of the commit message body is unchanged.

    Args:
        body: Squash-commit body text (may include trailers).

    Returns:
        Body with placeholder Co-authored-by lines removed.
    """
    if not body:
        return body

    filtered_lines = []
    for line in body.splitlines(keepends=True):
        match = _CO_AUTHOR_RE.match(line.rstrip("\n"))
        if match:
            name = match.group(1).strip()
            email = match.group(2).strip()
            if is_placeholder_identity(name, email):
                continue
        filtered_lines.append(line)
    return "".join(filtered_lines)
