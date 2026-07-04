#!/usr/bin/env python3
"""Reference patterns + line-level extractors for orphan-ref-validator.

Owns the regex constants and the line-by-line extractors. Each extractor
honors the line-scope `<!-- orphan-ref-ignore -->` directive.
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

IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore\s*-->")
FILE_IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore-file\s*-->")


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
