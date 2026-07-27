#!/usr/bin/env python3
"""Reference patterns + line-level extractors for orphan-ref-validator.

Owns the regex constants and the line-by-line extractors. Each extractor
honors the line-scope `<!-- orphan-ref-ignore -->` directive.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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
# Issue #3456 adds ``tests/`` so deleted test helpers referenced from specs
# fail the same script_path check instead of passing invisibly.
SCRIPT_REF_RE = re.compile(
    r"`(?<![\w/])((?:build/scripts|scripts/validation|scripts|tests)/[a-zA-Z0-9_/-]+\.(?:py|ps1))(?!\w)`",
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
    r"/(?:scripts|tests)/[a-zA-Z0-9_/-]+\.py(?!\w)",
    re.IGNORECASE,
)
RULE_REF_RE = re.compile(
    r"(?<![\w/])(\.claude/rules/[a-zA-Z0-9_.-]+\.md)(?!\w)",
    re.IGNORECASE,
)
INSTRUCTION_REF_RE = re.compile(
    r"(?<![\w/])((?:\.github|src/copilot-cli)/instructions/"
    r"[a-zA-Z0-9_.-]+\.instructions\.md)(?!\w)",
    re.IGNORECASE,
)
MARKDOWN_LINK_TARGET_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")

IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore\s*-->")
# Prose that explicitly types a token as a skill ("the `foo` skill", "skill
# `foo`", ``skill=`foo` ``). Such a reference asserts the token lives at
# .claude/skills/, so it must resolve against the skill catalog alone: an
# agent or memory of the same name does not make the claim true. REQ-009 AC-2
# requires the finding in that case. Bare mentions carry no type claim and may
# legally name a sibling artifact (see counts.py).
#
# Singular "skill" only. The plural reads as ordinary proficiency prose
# ("improve your `bash` skills") far more often than as a catalog reference,
# and a false positive here turns the /build gate red on a sentence that names
# no artifact at all. Bare-token resolution still covers plural list prose
# ("the `a`, `b`, and `c` skills") because each token is checked on its own.
SKILL_TYPED_REF_RE = re.compile(
    r"`(?P<after>[a-z][a-z0-9-]*)`\s+(?:is\s+(?:a|an|the)\s+)?skill\b"
    r"|\bskill\s+`(?P<before>[a-z][a-z0-9-]*)`"
    r"|\bskill\s*[=:]\s*[\"'`](?P<kv>[a-z][a-z0-9-]*)",
    re.IGNORECASE,
)
FILE_IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore-file\s*-->")
EXAMPLE_PLACEHOLDER_RE = re.compile(
    r"(^\s*(?:[-*]\s*)?(?:example:|e\.g\.|for example\b))"
    r"|((?:for example\b).*(?:was not created|does not exist|not present))",
    re.IGNORECASE,
)


def line_has_ignore_directive(line: str) -> bool:
    """True when the line carries an `<!-- orphan-ref-ignore -->` directive."""
    return bool(IGNORE_DIRECTIVE_RE.search(line))


def line_has_example_placeholder(line: str) -> bool:
    """True when a line is an example placeholder, not a real reference."""
    return bool(EXAMPLE_PLACEHOLDER_RE.search(line))


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
        if line_has_ignore_directive(line) or line_has_example_placeholder(line):
            continue
        for match in SCRIPT_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_skill_script_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(lineno, path)`` for skill-script references (.claude/skills or
    the copilot mirror), backticked or bare. De-duplicated per line so a path
    that appears backticked and inline is reported once."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line) or line_has_example_placeholder(line):
            continue
        seen: set[str] = set()
        for match in SKILL_SCRIPT_REF_RE.finditer(line):
            path = match.group(0)
            if path in seen:
                continue
            seen.add(path)
            yield lineno, path


def _iter_line_path_matches(
    line: str, pattern: re.Pattern[str]
) -> Iterable[str]:
    for match in pattern.finditer(line):
        yield match.group(1) if match.lastindex else match.group(0)
    for match in MARKDOWN_LINK_TARGET_RE.finditer(line):
        target = match.group(1).split("#", 1)[0]
        if target and pattern.fullmatch(target):
            yield target


def extract_rule_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(lineno, path)`` for rule file references."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line) or line_has_example_placeholder(line):
            continue
        seen: set[str] = set()
        for path in _iter_line_path_matches(line, RULE_REF_RE):
            if path in seen:
                continue
            seen.add(path)
            yield lineno, path


def extract_instruction_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(lineno, path)`` for generated instruction mirror references."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line) or line_has_example_placeholder(line):
            continue
        seen: set[str] = set()
        for path in _iter_line_path_matches(line, INSTRUCTION_REF_RE):
            if path in seen:
                continue
            seen.add(path)
            yield lineno, path


def extract_directive_suppressed_refs(text: str) -> Iterable[tuple[int, str]]:
    """Yield references hidden by a line-scope ignore directive."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line_has_ignore_directive(line):
            continue
        seen: set[str] = set()
        for pattern in (
            SCRIPT_REF_RE,
            SKILL_SCRIPT_REF_RE,
            RULE_REF_RE,
            INSTRUCTION_REF_RE,
            SKILL_REF_RE,
        ):
            for ref in _iter_line_path_matches(line, pattern):
                if ref in seen:
                    continue
                seen.add(ref)
                yield lineno, ref


def extract_typed_skill_refs(text: str) -> set[tuple[int, str]]:
    """Return ``(lineno, token)`` pairs the prose explicitly calls a skill.

    Used to decide resolution strictness, never to decide whether a token is
    a reference at all. A typed reference resolves against the skill catalog
    only; an untyped one may also resolve to a sibling artifact.
    """
    typed: set[tuple[int, str]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line_has_ignore_directive(line):
            continue
        for match in SKILL_TYPED_REF_RE.finditer(line):
            name = next(
                (g for g in match.groupdict().values() if g), None
            )
            if name:
                typed.add((lineno, name))
    return typed
