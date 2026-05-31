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
SCRIPT_REF_RE = re.compile(
    r"`((?:build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py)`"
)
# Skill-script references under .claude/skills/ or the copilot mirror, in
# either backticked or bare `python3 .../foo.py` command form. The bare form is
# intentional: issue #1987's failure was an unbackticked invocation of
# .claude/skills/github/scripts/pr/get_unresolved_threads.py (the real script is
# get_unresolved_review_threads.py). SCRIPT_REF_RE requires backticks and only
# the build/scripts|scripts/validation|scripts prefixes, so it misses this
# class. Existence is checked against the working tree; valid refs never flag.
SKILL_SCRIPT_REF_RE = re.compile(
    r"(?:\.claude|src/copilot-cli)/skills/[a-zA-Z0-9_-]+/scripts/[a-zA-Z0-9_/-]+\.py"
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
