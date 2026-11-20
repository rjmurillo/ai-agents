# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/fetchers/docs-conventions.ts  (the rule-section classifier, lines 21-63)
#   src/lib/fetchers/docs.ts              (splitIntoSections and the per-section filter,
#                                          lines 162-170 and 275-279)
# Sibling ports: adr_shape.py, adr_commits.py, adr_reason.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Pure classifiers for README, CONTRIBUTING and changelog sections that state a rule.

No file reads, no I/O, standard library only. The caller reads the Markdown and
passes the text. Upstream's minimum chunk length and co-change rule inference are
not ported.

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

__all__ = [
    "CHANGELOG_FILES",
    "CONTRIBUTING_FILES",
    "README_FILES",
    "DocKind",
    "RuleSection",
    "is_rule_section",
    "is_versioned_release_heading",
    "rule_sections",
    "section_body",
    "split_into_sections",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

# ---------------------------------------------------------------------------
# P13: rule sections of README, CONTRIBUTING and changelog
# (src/lib/fetchers/docs-conventions.ts, docs.ts)
# ---------------------------------------------------------------------------

README_FILES: tuple[str, ...] = ("README.md",)
CONTRIBUTING_FILES: tuple[str, ...] = (
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
)
CHANGELOG_FILES: tuple[str, ...] = (
    "CHANGELOG.md",
    "docs/changelog.md",
    "docs/CHANGELOG.md",
    "changelog.md",
)

DocKind = Literal["readme", "contributing", "changelog"]

# A line that states an obligation or prohibition.
_RULE_MARKER = re.compile(
    r"\b(?:must(?: not)?|never|always|every|do not|don't|required?|ensure|make sure|should)\b",
    _I,
)
# Headings under which a README section can be a rule. CONTRIBUTING needs no heading.
_CONVENTION_HEADING = re.compile(
    r"changelog|contribut|convention|guideline|\brules?\b|policy|versioning|release process"
    r"|commit|pull request|branch|review|style|deprecat|workflow|development|process"
    r"|branching|how to|standards?",
    _I,
)
# Headings a changelog uses for policy rather than history.
_CHANGELOG_POLICY_HEADING = re.compile(
    r"versioning|convention|policy|deprecat|contribut|guideline|\brules?\b|how to", _I
)
# Keep a Changelog's category headings: entries of one release, never policy.
_CHANGELOG_CATEGORY = re.compile(r"^(?:added|changed|deprecated|removed|fixed|security)\Z", _I)
# `[1.2.0] - 2026-01-01`, `2026-07-07`, `v2`, `Unreleased`: a release entry, never a rule.
_RELEASE_HEADING = re.compile(r"^\[?v?\d+(?:\.\d+)|^\[?unreleased\b|\d{4}-\d{2}(?:-\d{2})?", _I)
_VERSIONED_RELEASE_HEADING = re.compile(r"^release:?\s+v?\d", _I)
_H2_HEADING = re.compile(r"##\s+(.+)\Z", _A)
_NEXT_TOP_HEADING = re.compile(r"\n(?=#\s)", _A)
_TRAILING_RULE = re.compile(r"\n+-{3,}\s*\Z", _A)


class RuleSection(NamedTuple):
    heading: str
    body: str


def is_versioned_release_heading(heading: str) -> bool:
    """``Release: 1.2.0 batch landing``, ``Release 2.0``: a heading that names a version.

    "Release process" and "Releasing the installer" carry no version, so they are not
    release entries.
    """
    return bool(_VERSIONED_RELEASE_HEADING.search(heading.strip()))


def section_body(kind: DocKind, body: str) -> str:
    """Cut a changelog section where the next top-level heading starts.

    A changelog that uses ``# 1.2.0`` as a release heading puts the whole release
    inside the previous section's text.
    """
    return _NEXT_TOP_HEADING.split(body)[0].strip() if kind == "changelog" else body


def is_rule_section(kind: DocKind, heading: str, body: str) -> bool:
    """Does this section state a rule of the repository?

    A changelog policy section is a rule by its heading. Other kinds need a rule marker
    in the body, and a README also needs a convention heading.
    """
    if kind == "changelog":
        h = heading.strip()
        return not (
            _RELEASE_HEADING.search(h)
            or _CHANGELOG_CATEGORY.search(h)
            or not _CHANGELOG_POLICY_HEADING.search(h)
        )
    if not _RULE_MARKER.search(body):
        return False
    return kind == "contributing" or bool(_CONVENTION_HEADING.search(heading))


def split_into_sections(content: str) -> list[tuple[str | None, str]]:
    """Split Markdown on ``## `` headings into (heading, body) pairs.

    Content before the first heading is its own section with heading None. Line
    endings are normalised first, which upstream does not do for CRLF files.
    """
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in content.replace("\r\n", "\n").split("\n"):
        heading = _H2_HEADING.match(line)
        if heading:
            sections.append((heading.group(1).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def rule_sections(kind: DocKind, markdown: str) -> list[RuleSection]:
    """The sections of ``markdown`` that state a rule, in document order.

    Headingless preamble is skipped. A trailing ``---`` rule is removed from each body.
    Upstream's minimum chunk length and the co-change rule inference are not ported.
    """
    found: list[RuleSection] = []
    for heading, raw in split_into_sections(markdown):
        if not heading:
            continue
        body = _TRAILING_RULE.sub("", section_body(kind, raw)).strip()
        if is_rule_section(kind, heading, body):
            found.append(RuleSection(heading, body))
    return found
