# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/commit-shape.ts   (all of it)
#   src/lib/git.ts            (hasStatedRationale, isReasonBearingLine, resolveCommitShape,
#                              isDecisionCommit)
# Sibling ports: adr_commits.py (git.ts record parser, context-from-graph.ts), adr_docs.py
# (fetchers/docs-conventions.ts, fetchers/docs.ts), adr_reason.py (reason-extract.ts).
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Pure classifiers for commit subjects: is this one a decision, and does it say why?

No I/O, no subprocess, standard library only. Every function takes strings and
returns values. Covers the mechanical-subject filter, release and bump detection,
one-off titles, rule-stating subjects, numeric bounds, the commit rationale gate,
merge promotion and the decision-commit floor.

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

__all__ = [
    "CONVENTIONAL_PREFIX",
    "MECHANICAL_SUBJECT_PREFIXES",
    "MIN_DECISION_SUBJECT_CHARS",
    "STATED_WHY",
    "TITLE_CUT_AT",
    "CommitShape",
    "has_stated_rationale",
    "is_cut_title",
    "is_decision_commit",
    "is_housekeeping_title",
    "is_non_behavioural_type",
    "is_one_off_change_title",
    "is_reason_bearing_line",
    "is_release_or_bump_subject",
    "mechanical_subject_regex",
    "resolve_commit_shape",
    "states_numeric_bound",
    "states_subject_rule",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

# ---------------------------------------------------------------------------
# P1, P2, P3: commit subject shape (src/lib/commit-shape.ts)
# ---------------------------------------------------------------------------

MECHANICAL_SUBJECT_PREFIXES: tuple[str, ...] = (
    "chore",
    "wip",
    "merge",
    "revert",
    "bump",
    "update deps",
    "release",
    "typo",
)

# Below this many characters a subject is a label, not a decision.
MIN_DECISION_SUBJECT_CHARS = 20


def mechanical_subject_regex(prefixes: Iterable[str]) -> re.Pattern[str]:
    """The predicate's regex, built from the list with every prefix escaped.

    Anchored and case-insensitive. A prefix such as ``c++`` is matched literally.
    """
    escaped = "|".join(re.escape(p) for p in prefixes)
    return re.compile(f"^({escaped})", _I)


CONVENTIONAL_PREFIX = re.compile(r"^[a-z]+(?:\([^)]*\))?!?:\s*", _I)
_PR_REFERENCE = re.compile(r"\s*\(#\d+[^)]*\)", _A)
# "v5.9.0", "5.11.2", "Version 6.0.0-alpha.1": a subject that is only a version.
_VERSION_ONLY = re.compile(r"^(?:v(?:ersion)?\s*)?\d+\.\d+(?:\.\d+)?(?:[-+.][\w.-]+)?\Z", _I)
# "Bump", "Bumped v5.9.0", "Release 5.9.0": the word alone, or the word and a dotted version.
_BARE_BUMP_OR_RELEASE = re.compile(r"^(?:bump\w*|releas\w*)(?:\s*\Z|\s+v?\d+\.\d)", _I)
# One package token moving to a version, and nothing else. More words after the version,
# or a sentence in between ("Update docs for listening to 0.0.0.0"), is prose.
_DEPENDENCY_MOVE = re.compile(
    r"^(?:bump\w*|updat\w*|upgrad\w*)\s+(?:dependency\s+)?[@\w./-]+\s+"
    r"(?:from\s+v?\d[\w.-]*\s+)?(?:to\s+v?\d[\w.-]*)(?:\s+in\s.*|\s*\(.*\))?[.]?\Z",
    _I,
)
# A subject that says why is a decision whatever its shape.
STATED_WHY = re.compile(
    r"\b(?:because|so that|so we|so it|in order to|to keep|to avoid|to prevent|to ensure"
    r"|to make sure|due to|since|cve-\d+|drops?|dropping|security|breaking)\b",
    _I,
)


def is_release_or_bump_subject(subject: str) -> bool:
    """A release or version-bump subject with no stated reason.

    After any ``type(scope):`` and ``(#N)`` are removed, it is housekeeping when it is
    only a version, or the word bump/release alone or with a dotted version, or a
    bump/update/upgrade of something from or to a version, unless it states why.
    Dependency replacements ("replace a with b") are decisions and never match.
    """
    body = CONVENTIONAL_PREFIX.sub("", subject.strip(), count=1)
    body = _PR_REFERENCE.sub("", body).strip()
    if STATED_WHY.search(body):
        return False
    return bool(
        _VERSION_ONLY.search(body)
        or _BARE_BUMP_OR_RELEASE.search(body)
        or _DEPENDENCY_MOVE.search(body)
    )


# Conventional `type:` shapes only, git's own Merge subjects, and a [DRAFT/[WIP/[Backport
# marker (a backport repeats a decision made in the original).
_HOUSEKEEPING_SHAPE = re.compile(
    r"^(?:(?:docs|chore|ci|test|style|build)(?:\([^)]*\))?!?:"
    r"|merge\s+(?:pull request|branch|remote-tracking|tag)\b|\[(?:draft|wip|backport)\b)",
    _I,
)


def is_housekeeping_title(title: str) -> bool:
    """What a first-run listing must not show as a decision."""
    return bool(_HOUSEKEEPING_SHAPE.search(title.strip())) or is_release_or_bump_subject(title)


# The graph keeps a title as its first 80 characters, so one this long may be cut mid-word.
TITLE_CUT_AT = 80


def is_cut_title(title: str) -> bool:
    return len(title.strip()) >= TITLE_CUT_AT


_NON_BEHAVIOURAL_TYPE = re.compile(
    r"^(?:docs|style|test|chore|ci|build|release|refactor)(?:\([^)]*\))?!?:", _I
)


def is_non_behavioural_type(title: str) -> bool:
    """A conventional-commit type whose commits do not decide what the lines they touch do."""
    return bool(_NON_BEHAVIOURAL_TYPE.search(title.strip()))


_POLICY_WORD = re.compile(
    r"\b(?:adopt|requires?|standardi[sz]e[sd]?|enforce[sd]?|mandate[sd]?|deprecate[sd]?"
    r"|always|never|must|only|all|every|no longer|should(?: not)?|should(?:n't)?|do not"
    r"|don't)\b",
    _I,
)
_ONE_OFF_VERBS = re.compile(
    r"^(?:add|fix|rename|update|remove|bump|refactor|document|extend|post|put|modify|typo"
    r"|tidy)\b",
    _I,
)
_ONE_OFF_TYPES = frozenset({"fix", "test", "refactor", "chore", "ci", "docs", "style", "build"})
_TYPO = re.compile(r"\btypos?\b", _I)
_SWEEPING_QUANTIFIER = re.compile(r"\b(?:all|every)\b", _I)
_TYPE_PREFIX = re.compile(r"^([a-z]+)(?:\([^)]*\))?!?:\s*", _I)
# A stated numeric bound ("between 400 and 599", "no more than 5") is a rule, not a change note.
_NUMERIC_BOUND = re.compile(
    r"\b(?:between\s+\d+\s+and\s+\d+|(?:at least|at most|no more than|no less than|up to"
    r"|more than|less than|over|under|above|below)\s+\d+)\b",
    _I,
)


def states_numeric_bound(title: str) -> bool:
    """Does the title state a numeric bound? A title-only rule is kept by every filter."""
    return bool(_NUMERIC_BOUND.search(title))


# Types whose commits do not set how the code behaves, so a rule word in their title is
# about a test or a doc, not a decision.
_RULE_EXEMPT_TYPES = frozenset({"docs", "test", "tests", "chore", "ci", "style", "build"})
# A word that states a rule or a replacement. The lookarounds keep it from matching inside
# a package, file or code name ("fastify-https-always", "require.cache"). "deprecated" and
# "required" are left out on purpose: as adjectives they describe, they do not decide.
_SUBJECT_RULE = re.compile(
    r"(?<![-\w./])(?:do not|don't|never|must(?: not)?|should not|shouldn't|no longer|always"
    r"|disallow|forbid|deprecates?|in fav(?:o|ou)r of|instead of)(?![-\w./])",
    _I,
)


def states_subject_rule(title: str) -> bool:
    """Does a commit title state a rule on its own, with no body to say why?

    A prohibition or obligation ("do not force close ..."), a deprecation, or a
    replacement ("use X instead of Y"). Docs, test, chore, ci, style and build commits
    never count.
    """
    t = _PR_REFERENCE.sub("", title.strip()).strip()
    prefix = _TYPE_PREFIX.match(t)
    if prefix and prefix.group(1).lower() in _RULE_EXEMPT_TYPES:
        return False
    return bool(_SUBJECT_RULE.search(t[prefix.end() :] if prefix else t))


def is_one_off_change_title(title: str) -> bool:
    """Is this a title-only change note: a one-off lead with nothing that makes it a decision?

    A one-off lead (add, fix, rename, ... or a fix/test/refactor/chore/ci/docs/style/build
    type) is rescued by a stated purpose, a policy word, a sweeping quantifier, or a
    numeric bound. Anything that does not lead like that is not one-off.
    """
    t = _PR_REFERENCE.sub("", title.strip()).strip()
    prefix = _TYPE_PREFIX.match(t)
    if prefix:
        one_off = prefix.group(1).lower() in _ONE_OFF_TYPES or bool(_TYPO.search(t))
    else:
        one_off = bool(_ONE_OFF_VERBS.search(t) or _TYPO.search(t))
    if not one_off:
        return False
    body = t[prefix.end() :] if prefix else t
    return not (
        STATED_WHY.search(body)
        or _POLICY_WORD.search(body)
        or _SWEEPING_QUANTIFIER.search(body)
        or states_numeric_bound(body)
    )


# ---------------------------------------------------------------------------
# P4: commit rationale gate (src/lib/git.ts)
# ---------------------------------------------------------------------------

# A line that IS a git trailer, not a sentence that mentions one of these words mid-line.
_TRAILER_LINE = re.compile(
    r"^(co-authored-by|signed-off-by|reviewed-by|acked-by|helped-by|cc|refs?|closes?|fixes?"
    r"|resolves?)\s*:\s*\S",
    _I,
)
# Attribution lines an agent appends say who wrote the commit, not why. Anchored to the
# start of the line, past an optional bot emoji.
_GENERATED_WITH = re.compile(r"^(?:\U0001f916\s*)?generated (with|by)\b", _I)
# GitHub's squash-merge body is the PR's own commit list, a `---------` rule before the
# trailers, and "Modified 2 files" lines. All of it says WHAT changed.
_SEPARATOR_LINE = re.compile(r"^-{3,}\Z", _A)
_FILE_ACTION_LINE = re.compile(
    r"^(?:[*-]\s+)?(?:added|modified|deleted|renamed|removed)\s+(?:\d+\s+files?|\S*[/.]\S*)\s*\Z",
    _I,
)
_BULLET_LINE = re.compile(r"^[*-]\s+(.*)\Z", _A)
# A bullet with no stated why only counts as prose from this many words up.
_MIN_BULLET_WORDS = 8
_ECHO_BULLET = re.compile(r"^[*\-\u2022]\s*", _A)
_ECHO_SEPARATORS = re.compile(r"[^a-z0-9]+", _A)


def _normalize_for_echo(text: str) -> str:
    stripped = _ECHO_BULLET.sub("", text.lower(), count=1)
    return _ECHO_SEPARATORS.sub(" ", stripped).strip()


def is_reason_bearing_line(line: str) -> bool:
    """A plain line is evidence of a reason.

    A squash bullet is evidence only when it says why or is long enough to be a
    sentence. A bullet in ``type(scope): ...`` form is a subject however long it is.
    """
    bullet = _BULLET_LINE.match(line)
    if not bullet:
        return True
    text = bullet.group(1)
    if STATED_WHY.search(text):
        return True
    if CONVENTIONAL_PREFIX.search(text):
        return False
    return len(text.split()) >= _MIN_BULLET_WORDS


def has_stated_rationale(subject: str, body: str) -> bool:
    """Does the commit's body state a reason once the noise is stripped?

    A title that states a bound or a rule is a decision on its own. Otherwise trailers,
    agent attribution lines, echoes of the subject, separators, and file-action lines
    are dropped, and at least one reason-bearing line must remain.
    """
    if states_numeric_bound(subject) or states_subject_rule(subject):
        return True
    if not body.strip():
        return False
    subject_norm = _normalize_for_echo(subject)
    for raw in body.split("\n"):
        line = raw.strip()
        if _is_noise_line(line, subject_norm):
            continue
        if is_reason_bearing_line(line):
            return True
    return False


def _is_noise_line(line: str, subject_norm: str) -> bool:
    return (
        not line
        or bool(_TRAILER_LINE.search(line))
        or bool(_GENERATED_WITH.search(line))
        or _normalize_for_echo(line) == subject_norm
        or bool(_SEPARATOR_LINE.search(line))
        or bool(_FILE_ACTION_LINE.search(line))
    )


# ---------------------------------------------------------------------------
# P6: merge promotion and the decision-commit floor (src/lib/git.ts)
# ---------------------------------------------------------------------------

_MECHANICAL_SUBJECT = mechanical_subject_regex(MECHANICAL_SUBJECT_PREFIXES)
_MERGE_SUBJECT = re.compile(r"^merge\b", _I)
_TRAILING_PR_NUMBER = re.compile(r"\s*\(#\d+\)\s*\Z", _A)


class CommitShape(NamedTuple):
    subject: str
    body: str


def is_decision_commit(subject: str) -> bool:
    """Is this subject long enough and not mechanical, a release, a bump or a file action?"""
    trimmed = subject.strip()
    if len(trimmed) < MIN_DECISION_SUBJECT_CHARS:
        return False
    return (
        not _MECHANICAL_SUBJECT.search(trimmed)
        and not is_release_or_bump_subject(trimmed)
        and not _FILE_ACTION_LINE.search(_TRAILING_PR_NUMBER.sub("", trimmed))
    )


def resolve_commit_shape(subject: str, body: str) -> CommitShape:
    """Promote a merge commit's first body line to the subject when it is a decision.

    On GitHub's default merge flow the PR title and description live in the body. The
    original merge subject moves into the body so the ``#N`` PR reference survives.
    A merge with nothing decision-shaped in its body keeps its boilerplate subject.
    """
    if not _MERGE_SUBJECT.search(subject.strip()):
        return CommitShape(subject, body)
    lines = body.split("\n")
    first_index = next((i for i, line in enumerate(lines) if line.strip()), -1)
    first = "" if first_index == -1 else lines[first_index].strip()
    if not is_decision_commit(first):
        return CommitShape(subject, body)
    rest = "\n".join(lines[first_index + 1 :]).strip()
    return CommitShape(first, "\n".join(part for part in (subject, rest) if part))
