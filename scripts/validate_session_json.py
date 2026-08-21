#!/usr/bin/env python3
"""Validate a session log against the committed JSON Schema and protocol rules.

Two layers run, and they own different questions:

* ``.agents/schemas/session-log.schema.json`` owns shape: which fields exist,
  what type each holds, which values are in range. It is the single source of
  truth for that, loaded and enforced here rather than restated in Python.
* The protocol checks below own meaning: that a MUST checklist item is actually
  complete, that its evidence is not an empty string, that a branch name and a
  commit SHA look like one. A JSON Schema cannot express those.

Scope: this validates the one file it is handed. Its call site
(``git_hook_policy.validate_branch_sessions``) passes only session logs changed
on the branch, so enabling schema
enforcement binds new and edited logs. Logs written before enforcement are not
re-validated; editing one surfaces its violations, which is the intended signal.

This is a Python port of Validate-SessionJson.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Session log is valid
  1  - Error: Session log validation failed (invalid JSON, missing fields, or schema violations)
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema
from jsonschema import FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
_CLAUDE_LIB_DIR = _PROJECT_ROOT / ".claude" / "lib"
sys.path.insert(0, str(_CLAUDE_LIB_DIR))

from paths import artifact_dir  # noqa: E402
from qa_report import (  # noqa: E402
    session_log_identity,
    session_qa_binding,
    validate_qa_report,
)

from scripts.utils.path_validation import validate_safe_path  # noqa: E402
from scripts.validation.models import ValidationResult  # noqa: E402
from scripts.validation.session_scope import session_log_is_new  # noqa: E402

SCHEMA_PATH = _PROJECT_ROOT / ".agents" / "schemas" / "session-log.schema.json"

# jsonschema's built-in FormatChecker ships without a "date-time" checker
# unless the "format" extra (rfc3339-validator) is installed; that extra is
# not a project dependency. The committed schema declares `format:
# "date-time"` (developmentPhase.history[].timestamp), and by default
# jsonschema treats "format" as annotation-only, so that constraint was
# silently unenforced. datetime.fromisoformat (Python 3.11+, this project
# requires >=3.14) accepts RFC 3339's "Z" suffix, so a stdlib-only checker
# covers the one format the schema uses without adding a dependency. It is
# also looser than RFC 3339 on its own (see _check_date_time), which the
# tzinfo check below closes.
_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time")
def _check_date_time(value: object) -> bool:
    """Return whether ``value`` is an RFC 3339 date-time, per the schema's format.

    Non-strings are not this keyword's concern: JSON Schema's "format" applies
    only to the type it names, and "type": "string" elsewhere in the schema
    already rejects a non-string value.

    RFC 3339 section 5.6 requires a time-offset (``Z`` or a numeric offset);
    ``datetime.fromisoformat`` is looser and also accepts a naive timestamp
    with no offset at all, which would defeat the point of enforcing this
    format. Reject a parse that came back timezone-naive.
    """
    if not isinstance(value, str):
        return True
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


# Branch naming pattern
BRANCH_PATTERN = re.compile(r"^(feat|fix|docs|chore|refactor|test|ci)/")

# Commit SHA pattern
COMMIT_SHA_PATTERN = re.compile(r"^[a-f0-9]{7,40}$")

# The common default abbreviation length git uses. Longer abbreviations are
# possible when needed for uniqueness, but this is the heuristic threshold for
# recognising commit references in evidence text.
_SHORT_SHA = 7

# A conventional feature branch name. Anchored on the type prefix so that bare
# words in prose cannot match, and so that ``main`` never does.
_FEATURE_BRANCH_RE = re.compile(
    r"\b(?:feat|fix|docs|chore|refactor|test|ci|build|perf|style|revert)/[A-Za-z0-9._/-]+"
)

# A hex run long enough to be a commit abbreviation. Bounded on both sides so a
# 40-character SHA is read whole rather than as its first seven characters.
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

# Checklist items whose evidence answers "which branch did this session run
# on". Both spellings appear across the corpus.
_BRANCH_EVIDENCE_ITEMS = ("branchVerified", "notOnMain", "verifyBranch")

# Minimum required session start items (must exist in every session log).
#
# Four MUST items were once absent from this set (issue #4405), which made
# the gate strictly easier to satisfy by deleting a checklist item than by
# completing it: a deleted key was silent, an incomplete key failed. This is
# the sole source of truth for the checklist shape now; the generator this
# comment used to pin against (``new_session_log_json.py``) was deleted with
# the session-init skill (issue #5138), so a session log's checklist is
# written by hand and validated directly against this set.
SESSION_START_REQUIRED_ITEMS = frozenset(
    {
        "serenaActivated",
        "serenaInstructions",
        "handoffRead",
        "sessionLogCreated",
        "skillScriptsListed",
        "usageMandatoryRead",
        "constraintsRead",
        "memoriesLoaded",
        "branchVerified",
        "notOnMain",
    }
)

# Minimum required session end items (must exist in every session log)
SESSION_END_REQUIRED_ITEMS = frozenset(
    {
        "checklistComplete",
        "handoffPreserved",
        "serenaMemoryUpdated",
        "markdownLintRun",
        "qaValidation",
        "changesCommitted",
        "validationPassed",
    }
)

# Each QA exemption value owns one scope checker script (under
# scripts/validation/) and one label used in error messages. Both are
# verified the same way: run the checker over the recorded commit range,
# fail closed on any checker error, and report violations by path. See
# validate_qa_skip_scope.
_QA_SKIP_CHECKERS = {
    "SKIPPED: docs-only": ("test_docs_only_eligibility.py", "docs-only"),
    "SKIPPED: investigation-only": (
        "test_investigation_eligibility.py",
        "investigation-only",
    ),
}
_QA_SKIP_EVIDENCE = frozenset(_QA_SKIP_CHECKERS)

# Evidence patterns that contradict a "complete: true" claim
CONTRADICTION_PATTERNS = re.compile(
    r"(?i)\b(not available|skipped|N/A|deferred|will validate|will run|TODO|pending|TBD)\b"
)

# Subset of CONTRADICTION_PATTERNS tokens that legitimately describe a DIFFERENT
# scope than the item under validation. "deferred" and "pending" routinely appear
# in honest multi-scope evidence ("scorer deferred per PRD 11", "lint passed;
# pending pre-commit final run") where a different piece of work, not the item, is
# deferred. The other tokens (TODO, TBD, N/A, skipped, will run, will validate, not
# available) signal the item itself is incomplete and always flag, EXCEPT that a
# "skipped" token that is a numeric pytest outcome count is exempted separately
# (see _NUMERIC_COUNT_TOKENS and issue #3141). See issue #2007.
_SCOPE_QUALIFIED_TOKENS = frozenset({"deferred", "pending"})

# Words that affirmatively report the item itself was done. When such a word
# precedes a scope-qualified token across a clause boundary, the token is a
# trailing note about other work, not a contradiction of the item.
_AFFIRMATIVE_COMPLETION = re.compile(
    r"(?i)\b(pass|passed|passing|done|created|validated|complete|completed"
    r"|confirmed|verified|ran|listed|used)\b"
)

# A clause boundary separating affirmative completion from a trailing deferral.
# NOTE: Do NOT include ')' here. A closing paren allows false suppression when
# an affirmative word sits inside a parenthetical (e.g., "Report (tests passed)
# pending final sign-off" would suppress incorrectly). Legitimate trailing-note
# suppressions use '.' or ';' separators. See bug 80aca362.
#
# A period only counts as a boundary when it is sentence punctuation (followed
# by whitespace or end of string). A period flanked by digits is part of a
# version or decimal (`v1.5`, `Step 0.5`) and is NOT a clause boundary; treating
# it as one suppressed real contradictions like "Created item v1.5 pending
# review". See bug 0a163adc.
_CLAUSE_BOUNDARY = re.compile(r";|\.(?=\s|$)")

# Negation words that negate an affirmative completion.
# When an affirmative word is preceded by these, optionally separated by a
# single adverb ("not yet validated", "no longer confirmed", "not fully done"),
# it does not indicate completion (e.g., "not passed", "never confirmed").
# See bug ref1_1ef17459 and bug 07f14170 (adverb-separated negation).
# Note: "n't" uses (?<=\w) instead of \b because in contractions like "haven't",
# the "n" is preceded by a letter (no word boundary). See bug 0ea9d246.
_NEGATION_BEFORE_AFFIRMATIVE = re.compile(
    r"(?i)(?:\b(?:not|no|never)\b|(?<=\w)n't\b)"
    r"(?:\s+(?:yet|longer|fully|really|currently|still|quite))?\s*$"
)

# Adversative conjunctions. When one introduces the clause holding the deferral
# token, the deferral contradicts the preceding completion ("Tests passed. But
# we deferred the deploy") rather than noting separate work, so it must NOT be
# suppressed. See bug (gemini) on ordering/contrast false negatives.
_CONTRAST_CONJUNCTION = re.compile(r"(?i)\b(but|however|except|though|although)\b")

# pytest summarizes outcomes as counts like "21 skipped" or "45 xfailed". A
# "skipped" token that is immediately preceded by a digit (ignoring whitespace)
# is such a numeric test-outcome count, not a skipped validation step, so it must
# not flag as a contradiction. Only "skipped" collides with pytest count output;
# the other CONTRADICTION_PATTERNS tokens never appear as "<N> token" counts.
# See issue #3141.
#
# The count must be a standalone number: either at the start of the string or
# immediately after a delimiter (comma, semicolon, colon). This prevents false
# suppression when a numeric identifier precedes "skipped" (e.g. "step 21 skipped",
# "PR #3141 skipped", "v2.1 skipped") where the number is part of an identifier,
# not a pytest outcome count.
_NUMERIC_COUNT_TOKENS = frozenset({"skipped"})
_DIGIT_BEFORE_TOKEN = re.compile(r"(?:^|[,;:]\s*)\d+\s*$")
# pytest summary lines report counts as "<N> passed", "<N> skipped", etc. across
# multi-word summaries like "94 passed plus 1 skipped". The narrow prefix check
# in _DIGIT_BEFORE_TOKEN misses these when the count appears after a word (not a
# delimiter). This pattern recognises any "<N> outcome-word" in the full evidence
# string, acting as a secondary escape for the "skipped" token. Issue #3939.
_PYTEST_SUMMARY_CONTEXT = re.compile(r"\b\d+\s+(?:passed|failed|xfailed|xpassed|error(?:s)?)\b")

# Legacy field name for backward compatibility with existing session logs.
# Issue #868: "handoffNotUpdated" with Complete=false was a confusing double negative.
# New logs use "handoffPreserved" (level=MUST, Complete=true when satisfied).
_LEGACY_HANDOFF_FIELD = "handoffNotUpdated"


def get_case_insensitive(data: dict[str, Any], key: str) -> Any | None:  # noqa: ANN401
    """Get value from dict with case-insensitive key lookup.

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        Value if found, None otherwise.
    """
    for k, v in data.items():
        if k.lower() == key.lower():
            return v
    return None


def has_case_insensitive(data: dict[str, Any], key: str) -> bool:
    """Check if dict has key (case-insensitive).

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        True if key exists, False otherwise.
    """
    for k in data:
        if k.lower() == key.lower():
            return True
    return False


# Error prefixes that mark a MUST-level protocol failure. Used at both the
# emit sites below and by count_must_failures, so the counter cannot drift from
# the messages. Issue #3365: the CI workflow previously counted these with a
# regex for a markdown table this validator has never emitted, so the count was
# structurally pinned at zero.
_INCOMPLETE_MUST_PREFIX = "Incomplete MUST: "
_MISSING_REQUIRED_PREFIX = "Missing required item: "
_MUST_NOT_VIOLATED_PREFIX = "MUST NOT violated: "

# Every check in validate_must_item is gated on the item's own `level`, so a
# required item that declares no level at all is not merely unenforced: it is
# unread. Measured over the committed corpus, 138 required items carry no
# level, including 19 branchVerified and 4 notOnMain. Those are the two items
# that answer "did this session run on main", so the silent ones are the ones
# that matter most (issue #3747).
_MISSING_LEVEL_PREFIX = "Missing level: "

# A demotion from MUST to SHOULD requires documented justification.
# Enforcing that rule is what closes the demotion bypass: an author can
# still declare a required item SHOULD when
# the harness genuinely cannot satisfy it, but the deviation has to be written
# down and attributable. Measured over the corpus, all 257 existing demotions
# already carry evidence, so this enforces current practice rather than
# changing it.
_UNJUSTIFIED_DEMOTION_PREFIX = "Unjustified demotion: "

_MUST_FAILURE_PREFIXES: tuple[str, ...] = (
    _INCOMPLETE_MUST_PREFIX,
    _MISSING_REQUIRED_PREFIX,
    _MUST_NOT_VIOLATED_PREFIX,
    _MISSING_LEVEL_PREFIX,
    _UNJUSTIFIED_DEMOTION_PREFIX,
)


def count_must_failures(result: ValidationResult) -> int:
    """Count MUST-level failures among a result's errors.

    Args:
        result: A completed validation result.

    Returns:
        The number of errors that represent a MUST or MUST NOT violation.
        Schema and format errors are real failures but are not MUST-level.
    """
    return sum(1 for error in result.errors if error.startswith(_MUST_FAILURE_PREFIXES))


def validate_session_section(session: dict[str, Any], result: ValidationResult) -> None:
    """Validate the session section of the log.

    The schema owns shape: which fields exist and what types they hold. This
    function owns meaning: protocol checks the schema cannot express.

    Args:
        session: The session section data.
        result: ValidationResult to update with errors/warnings.
    """
    # Validate branch pattern. The type guard is load-bearing: schema errors are
    # collected rather than raised, so a log declaring a non-string branch still
    # reaches this line, and BRANCH_PATTERN.match would raise TypeError there.
    # That turns a reportable schema violation into a crash, which is the one
    # outcome a gate must not produce.
    branch = session.get("branch")
    if isinstance(branch, str) and branch and not BRANCH_PATTERN.match(branch):
        result.warnings.append(f"Branch '{branch}' doesn't follow conventional naming")

    # The creator records its host-local date (issue #4779). UTC+14 is the
    # furthest possible host offset, so reject dates later than the date there
    # at this instant as physically impossible (issue #3717).
    session_date_str = session.get("date")
    if isinstance(session_date_str, str):
        try:
            session_date = date.fromisoformat(session_date_str)
            now_utc = datetime.now(tz=timezone.utc)
            latest_host_date = (now_utc + timedelta(hours=14)).date()
            if session_date > latest_host_date:
                result.errors.append(
                    f"Session date '{session_date_str}' is in the future "
                    f"(later than the latest possible host date "
                    f"{latest_host_date.isoformat()} at {now_utc.isoformat()}); "
                    "that date is physically impossible for a current host and "
                    "looks like a placeholder or a wrong date"
                )
        except ValueError:
            pass  # Schema already rejects non-date strings via its pattern

    # Validate commit SHA format
    commit = session.get("startingCommit")
    if commit and not COMMIT_SHA_PATTERN.match(str(commit)):
        result.errors.append(f"Invalid commit SHA format: {commit}")


def _token_in_parentheses(text: str, token_start: int) -> bool:
    """Return True if the character at token_start sits inside an open parenthesis.

    Scans the prefix before the token tracking parenthesis depth. A positive
    depth means the token is part of a parenthetical aside.

    Args:
        text: Full evidence string.
        token_start: Index where the matched token begins.

    Returns:
        True if the token is inside unmatched parentheses.
    """
    depth = 0
    for char in text[:token_start]:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
    return depth > 0


def _is_scope_qualified(evidence: str, match: re.Match[str]) -> bool:
    """Return True if a contradiction token applies to a different scope.

    Only "deferred" and "pending" can be scope-qualified (see
    _SCOPE_QUALIFIED_TOKENS). They are treated as non-contradicting when either:

    1. The token sits inside a parenthetical aside, or
    2. An affirmative completion word precedes the token across a clause boundary
       (the evidence reports the item done, then notes other deferred work).
       A clause boundary is a semicolon, or a period acting as sentence
       punctuation (followed by whitespace or end of string); a period inside a
       version or decimal such as "v1.5" is not a boundary, and a closing
       parenthesis is deliberately excluded (parentheticals are handled by rule
       1 above).

    The affirmative completion must not be negated (directly or via an adverb,
    e.g. "not yet validated"), the clause boundary must sit BETWEEN the
    affirmative word and the token, and the deferral's own clause must not open
    with an adversative conjunction ("but", "however") that ties the deferral
    back to the completion.

    Every other token, and a bare "deferred"/"pending" with no affirmative
    context, always counts as a contradiction.

    Args:
        evidence: Full evidence string.
        match: A single CONTRADICTION_PATTERNS match within the evidence.

    Returns:
        True if the matched token describes a different scope (suppress warning).
    """
    if match.group(0).lower() not in _SCOPE_QUALIFIED_TOKENS:
        return False
    if _token_in_parentheses(evidence, match.start()):
        return True
    prefix = evidence[: match.start()]
    # Iterate over ALL affirmative matches, returning True if any non-negated
    # match has a clause boundary separating it from the deferral token AND no
    # adversative conjunction follows that boundary.
    for affirmative in _AFFIRMATIVE_COMPLETION.finditer(prefix):
        # Check if the affirmative word is negated (e.g., "not passed",
        # "not yet validated"). Negated affirmatives do not indicate completion.
        prefix_before_affirmative = prefix[: affirmative.start()]
        if _NEGATION_BEFORE_AFFIRMATIVE.search(prefix_before_affirmative):
            continue
        # The boundary must sit AFTER the affirmative word and before the token,
        # so search only the segment between them. Use the LAST boundary (not
        # first) so `deferral_clause` starts at the clause containing the actual
        # deferral token, not an intermediate clause. See bug a317fc68.
        suffix_after_affirmative = prefix[affirmative.end() :]
        boundaries = list(_CLAUSE_BOUNDARY.finditer(suffix_after_affirmative))
        if not boundaries:
            continue
        boundary = boundaries[-1]
        # If the deferral's clause opens with an adversative conjunction, the
        # deferral contradicts the completion rather than noting separate work.
        # Use match() on lstripped text to check only the clause opening, not
        # mid-clause uses like "everything but X". See bug ref1_dda37e6b.
        deferral_clause = suffix_after_affirmative[boundary.end() :].lstrip()
        if _CONTRAST_CONJUNCTION.match(deferral_clause):
            continue
        return True
    return False


def _is_numeric_test_count(evidence: str, match: re.Match[str]) -> bool:
    """Return True if the token is a pytest numeric outcome count.

    pytest reports outcomes as "<N> skipped" (for example
    "14434 passed, 21 skipped, 45 xfailed"). A digit immediately before a
    "skipped" token marks a test-outcome count, which is normal successful
    evidence, not a skipped validation step. See issue #3141.

    Args:
        evidence: Full evidence string.
        match: A single CONTRADICTION_PATTERNS match within the evidence.

    Returns:
        True if the matched token is a numeric test-outcome count.
    """
    if match.group(0).lower() not in _NUMERIC_COUNT_TOKENS:
        return False
    prefix = evidence[: match.start()]
    if bool(_DIGIT_BEFORE_TOKEN.search(prefix)):
        return True
    # _PYTEST_SUMMARY_CONTEXT must only apply to the clause that contains the
    # matched token. Searching the entire evidence string falsely excuses
    # "354 passed; markdownlint step skipped": "354 passed" satisfies the
    # pattern even though the "skipped" belongs to a different clause and is a
    # genuine contradiction. See post-#4001 adversarial review.
    clause_start = 0
    for sep in (";", "\n"):
        pos = evidence.rfind(sep, 0, match.start())
        if pos >= 0:
            clause_start = max(clause_start, pos + 1)
    clause_end = len(evidence)
    for sep in (";", "\n"):
        pos = evidence.find(sep, match.end())
        if 0 <= pos < clause_end:
            clause_end = pos
    clause = evidence[clause_start:clause_end].strip()
    return bool(_PYTEST_SUMMARY_CONTEXT.search(clause))


def _has_contradiction(evidence: str) -> bool:
    """Return True if evidence contradicts a "complete: true" claim.

    Flags any CONTRADICTION_PATTERNS token unless it is a scope-qualified
    "deferred"/"pending" that points at a different subject, or a "skipped"
    token that is a numeric pytest outcome count ("21 skipped"). A genuine
    contradiction (an item-itself deferral, "TODO", a bare token) still flags
    even when scope-qualified tokens appear elsewhere in the same string.

    Args:
        evidence: The evidence string to inspect.

    Returns:
        True if at least one unqualified contradiction token is present.
    """
    return any(
        not _is_scope_qualified(evidence, match) and not _is_numeric_test_count(evidence, match)
        for match in CONTRADICTION_PATTERNS.finditer(evidence)
    )


def _same_commit(cited: str, declared: str) -> bool:
    """Return True when two commit spellings can name the same commit.

    Git abbreviates to whatever length is unambiguous, so a log may hold a full
    SHA in one field and a seven-character prefix in another. Comparing the
    shorter against the longer is the only test that does not reject a correct
    record for spelling it two ways.

    Args:
        cited: A SHA read out of evidence prose.
        declared: The SHA the session section declares.

    Returns:
        True when either is a prefix of the other.
    """
    return cited.startswith(declared[: len(cited)]) or declared.startswith(cited[: len(declared)])


def _evidence_of(items: dict[str, Any], name: str) -> str:
    """Return the evidence string for a checklist item, or "" if absent.

    Args:
        items: A flattened checklist, item name to item.
        name: The checklist item to read.

    Returns:
        The evidence text, or "" when the item, the key, or a string value is
        missing. Callers treat "" as "nothing claimed", not as a violation.
    """
    item = items.get(name)
    if not isinstance(item, dict):
        return ""
    evidence = get_case_insensitive(item, "evidence")
    return evidence if isinstance(evidence, str) else ""


def _flatten_checklist(compliance: object) -> dict[str, Any]:
    """Return every checklist item keyed by name, ignoring its section.

    Item names are unique across sections in practice and the cross-field
    checks care about the fact, not where it was recorded. Logs in this repo
    spell the sections several ways (``sessionStart`` and ``session_start``
    both appear), so keying on section would make the checks miss the older
    half of the corpus.

    Args:
        compliance: The protocolCompliance value, whatever the parser produced.

    Returns:
        A flat name-to-item mapping; empty when the value is not a mapping of
        mappings.
    """
    flat: dict[str, Any] = {}
    if not isinstance(compliance, dict):
        return flat
    for section in compliance.values():
        if isinstance(section, dict):
            flat.update(section)
    return flat


def _contradicted_branches(evidence: str, branch: str) -> list[str]:
    """Return branches named in evidence that never names ``branch`` itself.

    Two narrowings, both measured against all 946 committed logs rather than
    reasoned about, because the obvious rule is wrong here.

    Only conventional ``type/slug`` names count. Evidence routinely mentions
    ``main`` and ``origin/main`` for legitimate reasons (a merge-base, a
    comparison), and counting those would flag most of the corpus.

    A second feature branch alone is *not* a contradiction either. Honest
    evidence names one whenever it describes a relationship: "renamed from
    feat/1774", "stacked on chore/lefthook-migration", "branched from
    feat/1769". Flagging on a second name caught seven logs, and six of the
    seven were exactly those. Contamination looks different: the evidence
    describes the other session and never mentions this branch at all.

    Args:
        evidence: The evidence text to read.
        branch: The branch the session section declares.

    Returns:
        The names found, empty when the evidence names no feature branch or
        names this one anywhere in the string.
    """
    named = _FEATURE_BRANCH_RE.findall(evidence)
    if any(name == branch or branch.startswith(name) or name.startswith(branch) for name in named):
        return []
    return named


def validate_evidence_agrees_with_session(data: dict[str, Any], result: ValidationResult) -> None:
    """Report evidence that describes a different session than the record does.

    Session logs are seeded by copying a recent log, so the previous session's
    evidence survives into the new record whenever the edit was incomplete. The
    schema cannot see this: every field is present and correctly typed, and the
    document is simply not true. These are facts stored twice with nothing
    enforcing agreement, the same defect class as issue #3355. See issue #3383.

    Only contradictions are reported, never silence. Evidence that names no
    branch and no commit is outside this function's reach; the completeness
    checks elsewhere own that case.

    Args:
        data: The whole log. These checks are cross-field by nature, so neither
            section validator can own them.
        result: ValidationResult to update with errors/warnings.
    """
    session = data.get("session")
    if not isinstance(session, dict):
        return
    items = _flatten_checklist(data.get("protocolCompliance"))

    branch = session.get("branch")
    if isinstance(branch, str) and branch:
        for name in _BRANCH_EVIDENCE_ITEMS:
            conflicting = _contradicted_branches(_evidence_of(items, name), branch)
            if conflicting:
                result.errors.append(
                    f"Evidence names a different branch: {name} cites "
                    f"{', '.join(sorted(set(conflicting)))} but session.branch is {branch!r}"
                )

    starting = session.get("startingCommit")
    if isinstance(starting, str) and len(starting) >= _SHORT_SHA:
        evidence = _evidence_of(items, "startingCommitNoted")
        cited = [sha for sha in _SHA_RE.findall(evidence) if len(sha) >= _SHORT_SHA]
        if cited and not any(_same_commit(sha, starting) for sha in cited):
            result.errors.append(
                f"Evidence names a different starting commit: startingCommitNoted cites "
                f"{', '.join(cited)} but session.startingCommit is {starting!r}"
            )

    committed = items.get("changesCommitted")
    claims_commit = isinstance(committed, dict) and (
        get_case_insensitive(committed, "complete") is True
    )
    ending = str(data.get("endingCommit") or "").strip()
    if claims_commit and not ending:
        result.warnings.append(
            "changesCommitted is complete but endingCommit is empty; "
            "record the final commit SHA or mark the item incomplete"
        )
    elif ending and COMMIT_SHA_PATTERN.match(ending):
        # A malformed value is the schema's to report; restating it here would
        # print the same fact under two spellings.
        #
        # Imported here rather than at module scope: every module-level import
        # in this file sits below a sys.path insert and so needs an E402
        # suppression, and a new suppression is exactly what the push gate
        # refuses. Function scope needs none, and the module is already loaded.
        from scripts.validation.session_scope import (
            NOT_AN_ANCESTOR,
            commit_reachability_problem,
        )

        problem = commit_reachability_problem(ending, _PROJECT_ROOT)
        if problem is not None:
            # State the observation and list only the candidates the check did
            # not already rule out. Naming one cause sends readers after a
            # mistake they did not make: this repository merges by squash,
            # which orphans every branch SHA a session log records. And when
            # the object is present but unreachable, `git cat-file -e` already
            # found it here, so it was pushed (issue #4347).
            causes = (
                "the PR was squash merged, which orphans the branch SHA; the "
                "commit was amended or rebased after the log named it"
            )
            if problem != NOT_AN_ANCESTOR:
                causes += "; the SHA was never pushed"
            result.errors.append(
                f"endingCommit {ending!r} {problem}. Candidate causes, most "
                f"likely first: {causes}. Record the SHA in a follow-up "
                "commit (issue #3618)"
            )

    # A session that committed cannot have its base equal its tip. When the log
    # is written after the work commit, startingCommit captures HEAD as it
    # already stands, so the two fields hold the same SHA. The episode extractor
    # excludes the base commit by design, so the session's only commit vanishes
    # and the episode records metrics.commits 0. The episode-store ratchet then
    # blocks the push naming the episode, several steps from the wrong field.
    # Reject the bad input here instead, where the field is (issue #4415).
    if (
        claims_commit
        and ending
        and isinstance(starting, str)
        and len(starting) >= _SHORT_SHA
        and _same_commit(ending, starting)
    ):
        result.errors.append(
            f"startingCommit and endingCommit are the same commit ({ending!r}) while "
            "changesCommitted is complete; a session's base cannot also be its tip. "
            "The log was most likely created after the work commit, so startingCommit "
            "captured HEAD rather than the base. Set startingCommit to the parent of "
            "the session's first commit. Left as-is, the extracted episode records "
            "metrics.commits 0 and the episode-store ratchet blocks the push (issue #4415)"
        )

    if "nextSteps" not in data:
        result.warnings.append(
            "nextSteps is missing; it is a required top-level field. Record "
            "the follow-ups, or write [] to state there are none"
        )


def _validate_required_item_level(
    level: object,
    is_complete: object,
    evidence: object,
    item_name: str,
    section_name: str,
    result: ValidationResult,
) -> None:
    """Stop a required item deciding how hard it will be checked.

    Every other check in ``validate_must_item`` reads the item's own ``level``,
    so the document controls its own enforcement. Two ways out of a MUST follow
    from that, and both are closed here.

    An absent ``level`` skips every branch, so the item is unread rather than
    merely lenient. A demotion to SHOULD silences an incomplete MUST outright,
    which is the bypass issue #3747 reports.

    Demotion stays legal, because a harness can genuinely lack a capability the
    protocol assumes: Serena is not reachable from Copilot CLI, and 61 logs say
    so. What it may no longer be is silent. Deviating from a MUST requires
    documented justification, so an incomplete demoted item without evidence
    is a protocol failure under the rule as written.
    """
    if level is None:
        result.errors.append(
            f"{_MISSING_LEVEL_PREFIX}{section_name}.{item_name} declares no level, "
            "so no requirement check applies to it. Required items must declare "
            'one ("MUST", "MUST NOT", or "SHOULD" with justification).'
        )
        return

    if level in ("MUST", "MUST NOT") or is_complete:
        return

    if not (isinstance(evidence, str) and evidence.strip()):
        result.errors.append(
            f"{_UNJUSTIFIED_DEMOTION_PREFIX}{section_name}.{item_name} is required "
            f"but declares level {level!r} while incomplete, with no evidence. "
            "Deviating from a MUST requires documented justification."
        )


def validate_must_item(
    check_data: object,
    item_name: str,
    section_name: str,
    result: ValidationResult,
    *,
    is_required: bool = False,
) -> None:
    """Validate a MUST requirement item.

    Args:
        check_data: The check item data.
        item_name: Name of the item being checked.
        section_name: Section name for error messages.
        result: ValidationResult to update with errors/warnings.
        is_required: Whether the schema names this item as required for the
            section. Required items answer to two extra rules, because for
            them the document must not be able to choose its own enforcement.
    """
    if not isinstance(check_data, dict):
        # Six committed logs from 2026-01 and 2026-02 store a bare boolean here
        # instead of the {complete, level, evidence} object. Reading .items()
        # off that raised AttributeError, which main() turned into "FATAL:
        # 'bool' object has no attribute 'items'" and exit 2. Exit 2 means the
        # validator broke, not the log, so the operator was sent to debug the
        # wrong file. Report it as what it is: a malformed item.
        result.errors.append(
            f"Malformed item: {section_name}.{item_name} is "
            f"{type(check_data).__name__}, not an object with complete/level/evidence"
        )
        return

    is_complete = get_case_insensitive(check_data, "complete")
    evidence = get_case_insensitive(check_data, "evidence")
    level = get_case_insensitive(check_data, "level")

    if is_required:
        _validate_required_item_level(level, is_complete, evidence, item_name, section_name, result)

    if level == "MUST" and not is_complete:
        result.errors.append(f"{_INCOMPLETE_MUST_PREFIX}{section_name}.{item_name}")

    if level == "MUST" and is_complete and not evidence:
        result.warnings.append(f"Missing evidence: {section_name}.{item_name}")

    if level == "MUST" and is_complete and evidence and isinstance(evidence, str):
        permitted_qa_skip = item_name == "qaValidation" and evidence in _QA_SKIP_EVIDENCE
        if not permitted_qa_skip and _has_contradiction(evidence):
            message = (
                f"Evidence contradiction: {section_name}.{item_name} "
                f"is complete but evidence suggests otherwise: {evidence!r}"
            )
            if item_name == "qaValidation":
                result.errors.append(message)
            else:
                result.warnings.append(message)


def validate_checklist_section(
    section_data: dict[str, Any],
    required_items: frozenset[str],
    section_name: str,
    result: ValidationResult,
) -> None:
    """Validate all MUST items in a checklist section.

    Checks both the minimum required items and any additional items
    in the section that declare level == "MUST".

    Args:
        section_data: The section data (e.g. sessionStart or sessionEnd).
        required_items: Minimum items that must exist in the section.
        section_name: Section name for error messages.
        result: ValidationResult to update with errors/warnings.
    """
    # Collect all items to validate: required items + any item with level MUST
    items_to_check: set[str] = set(required_items)
    for item_name, item_data in section_data.items():
        if isinstance(item_data, dict):
            level = get_case_insensitive(item_data, "level")
            if level in ("MUST", "MUST NOT"):
                items_to_check.add(item_name)

    for item_name in items_to_check:
        if item_name in section_data:
            validate_must_item(
                section_data[item_name],
                item_name,
                section_name,
                result,
                is_required=item_name in required_items,
            )
        else:
            result.errors.append(f"{_MISSING_REQUIRED_PREFIX}{section_name}.{item_name}")


def validate_session_start(session_start: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionStart section.

    Args:
        session_start: The sessionStart section data.
        result: ValidationResult to update with errors/warnings.
    """
    validate_checklist_section(session_start, SESSION_START_REQUIRED_ITEMS, "sessionStart", result)


def validate_session_end(session_end: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionEnd section.

    Args:
        session_end: The sessionEnd section data.
        result: ValidationResult to update with errors/warnings.
    """
    # Backward compatibility (issue #868): legacy logs use "handoffNotUpdated"
    # instead of "handoffPreserved". Swap the required item for legacy logs.
    required = SESSION_END_REQUIRED_ITEMS
    if _LEGACY_HANDOFF_FIELD in session_end and "handoffPreserved" not in session_end:
        required = (required - {"handoffPreserved"}) | {_LEGACY_HANDOFF_FIELD}

    validate_checklist_section(session_end, required, "sessionEnd", result)

    # Legacy MUST NOT check: Complete=true means HANDOFF.md was modified (violation).
    if _LEGACY_HANDOFF_FIELD in session_end and "handoffPreserved" not in session_end:
        check_data = session_end[_LEGACY_HANDOFF_FIELD]
        is_complete = get_case_insensitive(check_data, "complete")
        level = get_case_insensitive(check_data, "level")
        if level == "MUST NOT" and is_complete:
            result.errors.append(f"{_MUST_NOT_VIOLATED_PREFIX}HANDOFF.md was modified (read-only)")


def _resolve_full_commit(commit: str) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        return None
    resolved = completed.stdout.strip()
    return resolved or None


def validate_qa_report_evidence(
    data: dict[str, Any],
    session_end: dict[str, Any],
    result: ValidationResult,
    *,
    session_log: str | None,
    validation_head: str | None = None,
) -> None:
    """Require passing QA evidence bound to this session and validation commit."""
    qa_validation = get_case_insensitive(session_end, "qaValidation")
    if not isinstance(qa_validation, dict):
        return
    evidence = get_case_insensitive(qa_validation, "evidence")
    if not isinstance(evidence, str) or evidence in _QA_SKIP_EVIDENCE:
        return

    candidate = Path(evidence)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    qa_root = artifact_dir("qa", base=_PROJECT_ROOT).resolve()
    resolved_report = candidate.resolve()
    try:
        resolved_report.relative_to(qa_root)
    except ValueError:
        result.errors.append(
            "QA evidence must name a report under the configured QA "
            f"artifact root: {evidence!r}"
        )
        return
    if not resolved_report.is_file():
        result.errors.append(f"QA report not found: {resolved_report}")
        return

    try:
        if session_log is None:
            raise ValueError("Session log path is required for QA report binding")
        binding = session_qa_binding(
            data,
            session_log=session_log,
            resolve_commit=_resolve_full_commit,
        )
        # ADR-099: the session log's two commit fields are allowed to
        # disagree, because unrelated operations advance them. Report the
        # drift and carry on; warnings do not affect validity
        # (scripts/validation/models.py). Appended before the report is
        # validated so the observation survives an unrelated failure below.
        if binding.inconsistency is not None:
            result.warnings.append(binding.inconsistency)
        # ADR-096: `head` is required for staleness checking. Prefer an
        # explicitly resolved live-HEAD validation head, which catches
        # staleness from commits after the session's own recorded end
        # state; fall back to the session's own resolved commit
        # (`binding.commit`) when no such value is available, rather than
        # silently skipping the staleness check as the prior optional-
        # `validation_head` design did. This block runs only on the
        # fresh-validation path (`not existing_log and not creation_mode`,
        # see the caller above); the fallback fires when live-HEAD
        # resolution itself fails (a transient git error, or a checkout
        # `_resolve_full_commit` cannot parse), not on `--existing-log`,
        # which never reaches this function at all (round-2 correction,
        # ADR-096 Decision: round-1 review characterized this as reachable
        # on `--existing-log`, which the ADR's own gating one level up
        # rules out).
        head = validation_head if validation_head is not None else binding.commit
        validate_qa_report(resolved_report, binding, head=head, repo_root=_PROJECT_ROOT)
    except ValueError as exc:
        result.errors.append(str(exc))


def validate_protocol_compliance(
    protocol: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate the protocolCompliance section.

    Args:
        protocol: The protocolCompliance section data.
        result: ValidationResult to update with errors/warnings.
    """
    # protocolCompliance.required already names both sections, so the schema
    # reports either one missing. These guards exist only to hand the checks
    # below a mapping, not to restate that fact.
    if isinstance(protocol.get("sessionStart"), dict):
        validate_session_start(protocol["sessionStart"], result)

    if isinstance(protocol.get("sessionEnd"), dict):
        validate_session_end(protocol["sessionEnd"], result)


# Root fields promoted to schema-required by issue #3763, and the only ones an
# already-committed log is excused from. All six root fields have been
# required since the schema was written, and build_session_log emits all
# six, but the schema named only two, so the schema was the one document
# disagreeing with both. Renaming an old log still cannot conjure these four,
# so they relax in record mode (issue #3385).
_RELAXED_FOR_EXISTING_LOGS = frozenset({"schemaVersion", "workLog", "endingCommit", "nextSteps"})


def _load_schema() -> dict[str, Any]:
    """Read the committed schema.

    Not cached: this process validates one file and exits, so a cache would
    only hide a read error behind a stale hit.
    """
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


def _describe(error: jsonschema.ValidationError) -> str:
    """Render a schema violation with the path a contributor can act on."""
    location = ".".join(str(part) for part in error.absolute_path) or "(root)"
    return f"Schema: {location}: {error.message}"


def validate_against_schema(
    data: object, result: ValidationResult, *, existing_log: bool = False
) -> None:
    """Append every schema violation in ``data`` to ``result``.

    Reports all violations rather than the first, so one commit round fixes the
    log instead of one field per round. A missing or unreadable schema file, or
    a schema that is itself invalid, is an error, not a silent pass: the schema
    layer has checked nothing and must say so. This does not stop the protocol
    checks in ``validate_session_log``, which do not depend on the schema and
    still run for a dict-shaped payload.

    The validator comes from ``validator_for``, which reads the schema's own
    ``$schema`` key. The committed schema declares draft-07, and pinning a
    different draft here would silently change what several keywords mean.

    Passes ``_FORMAT_CHECKER`` so ``format`` keywords (currently just
    ``date-time``) are actually enforced instead of treated as annotations.

    ``check_schema`` runs before ``iter_errors`` rather than wrapping it in a
    ``SchemaError`` handler, because most malformed schemas do not raise that.
    A bad ``type`` name raises ``UnknownType`` and a non-object ``properties``
    raises ``AttributeError``, neither of which is a ``SchemaError``, so a
    handler alone still lets the gate die with a traceback. ``check_schema``
    validates against the metaschema and turns all of them into ``SchemaError``.
    It costs about 4ms against the committed schema.

    ``existing_log`` relaxes exactly the four root fields promoted to
    ``required`` for issue #3763. The rest of the schema still binds, because
    shape is always the record's own property (see ``validate_session_log``).
    Those four are the exception the #3385 rename case already established: a
    rename cannot supply a ``workLog`` the session never wrote down, and
    fabricating one to clear a gate is the behaviour that issue forbids.
    """
    try:
        schema = _load_schema()
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"Schema: cannot load {SCHEMA_PATH.name}, schema layer skipped: {exc}")
        return

    if not isinstance(schema, dict):
        result.errors.append(
            f"Schema: {SCHEMA_PATH.name} root is not a JSON object, schema layer skipped"
        )
        return

    if existing_log and isinstance(schema.get("required"), list):
        schema = {
            **schema,
            "required": [
                name for name in schema["required"] if name not in _RELAXED_FOR_EXISTING_LOGS
            ],
        }

    validator_cls = validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except SchemaError as exc:
        result.errors.append(
            f"Schema: {SCHEMA_PATH.name} is not a valid schema, schema layer skipped: {exc.message}"
        )
        return

    # Sorting by the raw path is safe. Two paths are only compared past a
    # shared prefix, and a shared prefix names one container, whose child keys
    # are therefore all strings (object) or all integers (array). Stringifying
    # to dodge a mixed comparison would order array index 10 before 2.
    validator = validator_cls(schema, format_checker=_FORMAT_CHECKER)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        result.errors.append(_describe(error))


def validate_session_log(
    data: object,
    *,
    existing_log: bool = False,
    creation_mode: bool = False,
    session_log: str | None = None,
    validation_head: str | None = None,
) -> ValidationResult:
    """Validate a session log against the committed schema and protocol rules.

    Args:
        data: Whatever ``json.loads`` produced. A session log is an object, but
            any JSON value can reach here, so the type is the parser's, not the
            schema's. The schema reports a non-object; the protocol checks below
            need a mapping and are skipped without one.
        creation_mode: True when the log was just created and session-end
            evidence does not yet exist. The full schema still binds (required
            fields, correct types, ``notOnMain``), but ``validate_protocol_compliance``
            and ``validate_evidence_agrees_with_session`` are skipped because
            the session has not run yet. Use this at creation time only; use
            ``existing_log`` for logs already committed. The two modes are
            mutually exclusive; if both are set, ``existing_log`` wins.
        existing_log: True when the log was already committed and this change
            only edits it. Two different questions are bundled in this file, and
            they have different answers on an old log. Shape ("is this record
            well formed") is always the log's own property and always binds.
            Checklist completeness ("did the session run markdownlint") is a
            property of a session that already ended: it cannot be made true by
            editing the record, and demanding it is a demand to invent evidence.
            So an existing log is validated as a record, and a new one is
            validated as a record *and* as a compliance claim. See issue #3385.

            Agreement between evidence and the session section sits on the
            claim side of that line, which is not obvious and is worth stating.
            The record's shape is "branchVerified holds an evidence string";
            whether that string describes *this* session is a claim about how
            the session was conducted. It matters practically: four committed
            logs contradict themselves, and git cannot adjudicate which side is
            true, so on the record side those four would be a permanent block
            that no honest edit could clear. See issue #3383.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    validate_against_schema(data, result, existing_log=existing_log)

    # A valid session log must be a JSON object at the root. If it's not (e.g.,
    # an array or primitive), the schema validation above already reported the
    # error; we cannot run protocol checks on a non-mapping value.
    if not isinstance(data, dict):
        return result

    # The schema already reported either section as missing. Restating it here
    # would print the same fact twice under two spellings; these branches exist
    # only so the protocol checks below get a mapping to walk.
    if isinstance(data.get("session"), dict):
        validate_session_section(data["session"], result)

    # creation_mode: the session just started; checklist items are incomplete
    # by design and evidence-agreement checks have nothing to compare against.
    # existing_log wins when both are set (see docstring).
    skip_compliance = existing_log or creation_mode
    if not skip_compliance and isinstance(data.get("protocolCompliance"), dict):
        validate_protocol_compliance(data["protocolCompliance"], result)

    if not existing_log and not creation_mode:
        validate_evidence_agrees_with_session(data, result)

    protocol = data.get("protocolCompliance")
    session_end = (
        get_case_insensitive(protocol, "sessionEnd")
        if isinstance(protocol, dict)
        else None
    )
    if not existing_log and not creation_mode and isinstance(session_end, dict):
        validate_qa_report_evidence(
            data,
            session_end,
            result,
            session_log=session_log,
            validation_head=validation_head,
        )

    return result


def _qa_skip_claim(data: object) -> tuple[str, object, object] | None:
    """Return the evidence and recorded range for a recognized QA skip."""
    if not isinstance(data, dict):
        return None
    protocol = data.get("protocolCompliance")
    if not isinstance(protocol, dict):
        return None
    session_end = get_case_insensitive(protocol, "sessionEnd")
    if not isinstance(session_end, dict):
        return None
    qa_validation = get_case_insensitive(session_end, "qaValidation")
    if not isinstance(qa_validation, dict):
        return None
    evidence = get_case_insensitive(qa_validation, "evidence")
    if not isinstance(evidence, str) or evidence not in _QA_SKIP_EVIDENCE:
        return None

    session = data.get("session")
    starting_commit = (
        get_case_insensitive(session, "startingCommit")
        if isinstance(session, dict)
        else None
    )
    return evidence, starting_commit, data.get("endingCommit")


def _scope_payload(
    checker_name: str,
    starting_commit: str,
    ending_commit: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run the owning eligibility checker for one recorded commit range."""
    checker = _PROJECT_ROOT / "scripts" / "validation" / checker_name
    if not checker.is_file():
        return None, f"scope checker not found: {checker}"

    completed = subprocess.run(
        [
            sys.executable,
            str(checker),
            "--base-ref",
            starting_commit,
            "--head-ref",
            ending_commit,
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        return None, f"scope checker failed: {detail}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, "scope checker returned invalid JSON"
    if not isinstance(payload, dict):
        return None, "scope checker returned non-object JSON"
    return payload, None


def validate_qa_skip_scope(
    data: object,
    result: ValidationResult,
    *,
    validation_head: str | None = None,
) -> None:
    """Verify a docs-only or investigation-only QA claim through its checker."""
    claim = _qa_skip_claim(data)
    if claim is None:
        return
    evidence, starting_commit, ending_commit = claim
    checker_name, label = _QA_SKIP_CHECKERS[evidence]
    if not isinstance(starting_commit, str) or not isinstance(ending_commit, str):
        result.errors.append(
            f"QA {label} scope cannot be verified: "
            "startingCommit and endingCommit are required"
        )
        return

    payload, error = _scope_payload(
        checker_name,
        starting_commit,
        validation_head or ending_commit,
    )
    if error:
        result.errors.append(f"QA {label} {error}")
        return
    assert payload is not None
    error = payload.get("Error")
    if error:
        result.errors.append(f"QA {label} scope cannot be verified: {error}")
        return
    if not payload.get("Eligible", False):
        violations = payload.get("Violations", [])
        detail = ", ".join(str(path) for path in violations) or "unknown changed path"
        result.errors.append(f"QA {label} scope includes disqualifying changes: {detail}")


_FILENAME_NUMBER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-session-(\d+)(?:-|$)")


def filename_session_number(session_path: Path) -> int | None:
    """Read the session number encoded in a session log filename.

    Args:
        session_path: Path to the session log file.

    Returns:
        The integer following ``session-`` in a ``YYYY-MM-DD-session-N`` stem,
        or None when the stem does not carry one. The digit run must end at a
        hyphen or the end of the stem: six committed logs predate the convention
        and use a non-numeric discriminator (``session-64a-``, ``session-2993b-``,
        ``session-critic-468-``), and reading a truncated ``64`` out of ``64a``
        would fail a file the convention never covered.
    """
    match = _FILENAME_NUMBER_PATTERN.match(session_path.stem)
    if match is None:
        return None
    return int(match.group(1))


def validate_filename_number(
    session_path: Path,
    data: object,
    result: ValidationResult,
) -> None:
    """Check that ``session.number`` matches the number in the filename.

    The log filename is derived from ``session.number`` and downstream
    tooling reads the number back out of the filename, so the two are one fact
    stored twice. Nothing enforced the agreement, which let an autofix bot seed a
    counter value that disagreed with the name it was written under (issue #3355).

    The related invariant proposed in that issue, that the number tracks the issue
    in the branch name, is not the convention. Most committed logs on an issue
    branch disagree, because sessions routinely work a branch owned by a
    different issue. Branch-to-log correspondence is enforced separately by the
    branch-context policy at push time. The measurement behind that finding is
    in the issue and in the PR description, where it can age without turning
    this docstring into a lie.

    Args:
        session_path: Path the log was loaded from.
        data: Parsed session log.
        result: Result to append any violation to.
    """
    expected = filename_session_number(session_path)
    if expected is None:
        return

    if not isinstance(data, dict):
        return

    session = data.get("session")
    if not isinstance(session, dict):
        return

    number = session.get("number")
    # A missing or mistyped number is the schema's finding to report, not this
    # one. Restating it here would print the same defect under two spellings.
    # bool is an int subclass, so it has to be excluded explicitly.
    if not isinstance(number, int) or isinstance(number, bool):
        return

    if number != expected:
        result.errors.append(
            f"session.number ({number}) does not match the number in the filename "
            f"({expected}): {session_path.name}. These are the same fact stored twice. "
            f"Set session.number to {expected}, or rename the file to carry {number} "
            f"if the number is the correct one."
        )


def load_session_file(session_path: Path) -> tuple[object | None, str | None]:
    """Load and parse a session log file.

    Args:
        session_path: Path to the session log file.

    Returns:
        Tuple of (parsed data, error message). Data is None if error occurred.
        The data may be any valid JSON value (object, array, string, etc.).
    """
    if not session_path.exists():
        return None, f"Session file not found: {session_path}"

    try:
        content = session_path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"Could not read session file: {e}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in session file: {session_path}"
        error_msg += f"\nSyntax error at line {e.lineno}, position {e.colno}"

        # Show context
        lines = content.split("\n")
        if e.lineno <= len(lines):
            error_msg += f"\nNear: {lines[e.lineno - 1]}"

        error_msg += f"\nError details: {e.msg}"
        error_msg += "\n\nCommon fixes:"
        error_msg += "\n  - Remove trailing commas from arrays/objects"
        error_msg += "\n  - Ensure all strings are properly quoted"
        error_msg += f"\n  - Validate JSON structure with: python -m json.tool '{session_path}'"

        return None, error_msg

    return data, None


def report_results(
    session_path: Path,
    result: ValidationResult,
    pre_commit: bool = False,
) -> None:
    """Report validation results to stdout.

    Args:
        session_path: Path to the session file.
        result: Validation result to report.
        pre_commit: If True, use compact output for pre-commit hook.
    """
    if not pre_commit:
        print()
        print("=== Session Validation ===")
        print(f"File: {session_path}")

    if result.is_valid:
        if not pre_commit:
            print()
            print("[PASS] Session log is valid")
    else:
        if pre_commit:
            print("Session validation FAILED:")
            for error in result.errors:
                print(f"  {error}")
        else:
            print()
            print("[FAIL] Validation errors:")
            for error in result.errors:
                print(f"  - {error}")

    if result.warnings and not pre_commit:
        print()
        print("[WARN] Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")


def _repo_relative(path: Path) -> str:
    """Return ``path`` as a repo-relative POSIX path for scope detection.

    ``session_scope`` compares paths against ``git diff --name-status`` and
    ``git ls-files`` output, both of which report repo-relative POSIX paths.
    An absolute path would never match. A path outside the repository is
    returned unchanged; the scope probe then treats it as new, which is the
    strict answer.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(_PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _session_roots() -> tuple[Path, ...]:
    """Return configured and repository-default physical session roots."""
    configured = artifact_dir("sessions", base=_PROJECT_ROOT).resolve()
    default = (_PROJECT_ROOT / ".agents" / "sessions").resolve()
    return tuple(dict.fromkeys((configured, default)))


def _validate_session_path(path: str | Path) -> Path:
    """Accept a session file under the repository or configured artifact root."""
    roots = tuple(dict.fromkeys((_PROJECT_ROOT, *_session_roots())))
    for root in roots:
        try:
            return validate_safe_path(path, root)
        except (ValueError, FileNotFoundError):
            continue
    raise ValueError(
        f"Path {path} is outside the repository and configured sessions root"
    )


def _session_identity(path: Path) -> str:
    """Return the canonical logical identity for a physical session file."""
    for sessions_root in _session_roots():
        try:
            return cast(
                str,
                session_log_identity(path, sessions_root=sessions_root),
            )
        except ValueError:
            continue
    raise ValueError(f"Session log is outside every supported sessions root: {path}")


def _session_identity_override(value: str) -> str:
    """Validate and canonicalize a logical session identity from the CLI."""
    return _session_identity(_PROJECT_ROOT / Path(value))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "session_path",
        type=Path,
        help="Path to the session log JSON file",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Suppress verbose output when called from pre-commit hook",
    )
    parser.add_argument(
        "--existing-log",
        action="store_true",
        help=(
            "Skip protocol-compliance and evidence-agreement checks: validate "
            "schema and shape only. Use for a log already committed where "
            "a checklist item cannot be made true retroactively."
        ),
    )
    parser.add_argument(
        "--creation-mode",
        action="store_true",
        help=(
            "Validate a freshly created log: full schema check plus structural "
            "shape, but skip protocol-compliance (checklist items are incomplete "
            "by design) and evidence-agreement (nothing to agree against yet). "
            "Use only at session-creation time; use --existing-log for already-"
            "committed logs."
        ),
    )
    parser.add_argument(
        "--scope-from-git",
        action="store_true",
        help=(
            "Derive --existing-log from git: a log already present at the "
            "merge base with origin/main is validated as a record. Use this "
            "where computing the scope out-of-band would restate the rule."
        ),
    )
    parser.add_argument(
        "--session-log-identity",
        help=(
            "Use this repository-relative logical session path for QA binding "
            "when validating a ref-backed temporary copy."
        ),
    )
    parser.add_argument(
        "--validation-head",
        help=(
            "Validate investigation-only scope through this commit instead of "
            "stopping at the recorded endingCommit."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        metavar="PATH",
        help=(
            "Also write a machine-readable summary to PATH. Human-readable "
            "output on stdout is unchanged, so this is safe to add to any "
            "existing caller."
        ),
    )
    return parser.parse_args()


def build_summary(session_path: Path, result: ValidationResult) -> dict[str, Any]:
    """Build the machine-readable summary emitted by --json-output.

    Args:
        session_path: Path to the validated session log.
        result: The completed validation result.

    Returns:
        A JSON-serialisable summary. `must_failures` counts only MUST-level
        violations; `errors` holds every error including schema failures, so
        `must_failures` can legitimately be 0 on a NON_COMPLIANT verdict.
    """
    return {
        "file": str(session_path),
        "verdict": "COMPLIANT" if result.is_valid else "NON_COMPLIANT",
        "exit_code": 0 if result.is_valid else 1,
        "must_failures": count_must_failures(result),
        "error_count": len(result.errors),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 on validation failure, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Validate the user-provided path against the project root
        try:
            validated_path = _validate_session_path(args.session_path)
        except (ValueError, FileNotFoundError) as e:
            print(f"ERROR: Invalid path provided: {e}", file=sys.stderr)
            return 1

        # Load session file using the validated path
        # load_session_file returns (data, error) where error is non-None only
        # for I/O or parse failures. A JSON `null` root is valid JSON that
        # parses to Python None with no error; that case must reach schema
        # validation, which will reject the non-object root with a clear message.
        data, error = load_session_file(validated_path)
        if error is not None:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

        # Validate session log
        existing_log = args.existing_log
        if args.scope_from_git and not existing_log:
            existing_log = not session_log_is_new(
                _repo_relative(validated_path),
                _PROJECT_ROOT,
            )

        validation_head = args.validation_head
        if not existing_log and not args.creation_mode and validation_head is None:
            validation_head = _resolve_full_commit("HEAD")
        if args.session_log_identity:
            try:
                session_log = _session_identity_override(args.session_log_identity)
            except ValueError as exc:
                print(f"ERROR: Invalid session identity: {exc}", file=sys.stderr)
                return 1
        else:
            try:
                session_log = _session_identity(validated_path)
            except ValueError:
                session_log = _repo_relative(validated_path)
        result = validate_session_log(
            data,
            existing_log=existing_log,
            creation_mode=args.creation_mode,
            session_log=session_log,
            validation_head=validation_head,
        )
        validate_filename_number(validated_path, data, result)
        validate_qa_skip_scope(
            data,
            result,
            validation_head=args.validation_head,
        )

        # Report results
        report_results(validated_path, result, args.pre_commit)

        if args.json_output is not None:
            summary = build_summary(validated_path, result)
            args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

        return 0 if result.is_valid else 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
