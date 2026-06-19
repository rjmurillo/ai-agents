#!/usr/bin/env python3
"""Reference patterns + line-level extractors for orphan-ref-validator.

Owns the regex constants and the line-by-line extractors. Each extractor
honors the line-scope `<!-- orphan-ref-ignore -->` directive.

The ``COUNT_CLAIM_RE`` and ``COUNT_LABEL_MAP`` mirror
``build/scripts/validate_marketplace_counts.py:COUNT_PATTERN`` and
``LABEL_MAP`` byte-for-byte. Per ``.claude/rules/canonical-source-mirror.md``
the canonical contract is quoted in the docstring of ``COUNT_CLAIM_RE``
below; the orphan-ref-validator does not implement the canonical's --fix
path or YAML-driven per-plugin exclude resolution.
"""

from __future__ import annotations

import re
from typing import Iterable

SKILL_REF_RE = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")
# Single-token (no-hyphen) backticked skill names. SKILL_REF_RE requires at
# least one ``-<group>``, so backticked single-word skills (``incoherence``,
# ``workflow``, ``memory``, ``reflect``, ``analyze``, ``session``) never match
# it, and deleting such a skill yields zero orphan-ref findings even when prose
# still references it (issue #2679; observed retiring `incoherence`, #2662).
# This regex casts the wide net of every backticked lowercase word; the scanner
# narrows that to genuine skill references by intersecting against the live
# ``.claude/skills/`` catalog and the curated ``KNOWN_SINGLE_WORD_SKILLS`` set
# (see ``_check_skill_refs`` in scan.py). The regex alone MUST NOT be treated as
# a skill-reference oracle: most single backticked words are prose, not skills.
SINGLE_WORD_SKILL_REF_RE = re.compile(r"`([a-z][a-z0-9]*)`")
# Backticked repo-relative script references under the standard prefixes.
# PR2 (issue #1994) broadens the suffix from ``.py`` only to ``.py`` or
# ``.ps1``: PowerShell helpers under these prefixes are referenced in specs
# (e.g. backticked `scripts/Validate-SessionEnd.ps1`) and went undetected.
# This regex is NOT under the canonical-source-mirror contract; only
# COUNT_CLAIM_RE / COUNT_LABEL_MAP mirror the canonical validator.
SCRIPT_REF_RE = re.compile(
    r"`(?<![\w/])((?:build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.(?:py|ps1))(?!\w)`",
    re.IGNORECASE,
)
# Skill-script references under .claude/skills/ or the copilot mirror, in
# either backticked or bare `python3 .../foo.py` command form. The bare form is
# intentional: issue #1987's failure was an unbackticked invocation of
# .claude/skills/github/scripts/pr/get_unresolved_threads.py (the real script is
# get_unresolved_review_threads.py). SCRIPT_REF_RE requires backticks and only
# the build/scripts|scripts/validation|scripts prefixes, so it misses this
# class. Existence is checked against the working tree; valid refs never flag.
SKILL_SCRIPT_REF_RE = re.compile(
    r"(?<![\w/])(?:\.claude|src/copilot-cli)/skills/[a-zA-Z0-9_-]+"
    r"/scripts/[a-zA-Z0-9_/-]+\.py(?!\w)",
    re.IGNORECASE,
)

# Mirrors COUNT_PATTERN and LABEL_MAP from
# build/scripts/validate_marketplace_counts.py (canonical):
#
#     COUNT_PATTERN = re.compile(
#         r"(\d+)\s+"
#         r"(specialized\s+agent\s+definition"
#         r"|agent\s+definition"
#         r"|agent"
#         r"|slash\s+command"
#         r"|lifecycle\s+hook"
#         r"|reusable\s+skill)"
#         r"s?"
#     )
#     LABEL_MAP = {
#         "specialized agent definition": "agent",
#         "agent definition": "agent",
#         "agent": "agent",
#         "slash command": "slash command",
#         "lifecycle hook": "lifecycle hook",
#         "reusable skill": "reusable skill",
#     }
COUNT_CLAIM_RE = re.compile(
    r"(\d+)\s+"
    r"(specialized\s+agent\s+definition"
    r"|agent\s+definition"
    r"|agent"
    r"|slash\s+command"
    r"|lifecycle\s+hook"
    r"|reusable\s+skill)"
    r"s?"
)
COUNT_LABEL_MAP = {
    "specialized agent definition": "agent",
    "agent definition": "agent",
    "agent": "agent",
    "slash command": "slash command",
    "lifecycle hook": "lifecycle hook",
    "reusable skill": "reusable skill",
}

IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore\s*-->")
FILE_IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore-file\s*-->")
_WHITESPACE_RE = re.compile(r"\s+")


def line_has_ignore_directive(line: str) -> bool:
    """True when the line carries an `<!-- orphan-ref-ignore -->` directive."""
    return bool(IGNORE_DIRECTIVE_RE.search(line))


def extract_skill_refs(text: str) -> Iterable[tuple[int, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        for match in SKILL_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_single_word_skill_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(lineno, token)`` for backticked single-word lowercase tokens.

    Casts a wide net (every ``\\`word\\``` matches); the scanner narrows this to
    genuine skill references in ``_check_skill_refs``. Tokens that contain a
    hyphen are handled by ``extract_skill_refs`` and are not re-emitted here:
    ``SINGLE_WORD_SKILL_REF_RE`` has no hyphen group, so a hyphenated backtick
    span never matches as a whole token.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        for match in SINGLE_WORD_SKILL_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_script_refs(text: str) -> Iterable[tuple[int, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        for match in SCRIPT_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_skill_script_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(lineno, path)`` for skill-script references (.claude/skills or
    the copilot mirror), backticked or bare. De-duplicated per line so a path
    that appears backticked and inline is reported once."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        seen: set[str] = set()
        for match in SKILL_SCRIPT_REF_RE.finditer(line):
            path = match.group(0)
            if path in seen:
                continue
            seen.add(path)
            yield lineno, path


def extract_count_claims(text: str) -> Iterable[tuple[int, int, str]]:
    """Yield ``(lineno, count, canonical_label)`` triples.

    ``canonical_label`` is the ``COUNT_LABEL_MAP`` value (one of "agent",
    "slash command", "lifecycle hook", "reusable skill"); upstream
    enumerators consume the same labels.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        for match in COUNT_CLAIM_RE.finditer(line):
            label_text = _WHITESPACE_RE.sub(" ", match.group(2).lower())
            canonical = COUNT_LABEL_MAP.get(label_text)
            if canonical is None:
                continue
            yield lineno, int(match.group(1)), canonical
