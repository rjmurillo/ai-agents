#!/usr/bin/env python3
"""Curated filter sets for orphan-ref-validator.

Houses the curated allowlists that decide which kebab-case and
single-word tokens are candidate skill references. Kept in a separate
module so ``scan.py`` stays under the 500-line file-size lint cap.
"""

from __future__ import annotations

import re

MODEL_ID_RE = re.compile(r"^claude-(opus|sonnet|haiku)-\d")



# Hyphenated skill names that are genuinely absent from the live catalog but
# existed as skills in repository history. This is the kebab counterpart of
# KNOWN_SINGLE_WORD_SKILLS below and is governed by the same contract: the set
# widens detection, the live catalog still decides validity.
#
# Two surfaces consume it, with different strictness.
#
# Prose-heavy targets such as Serena memories report a missing-skill claim only
# when the line is typed AND the token is in this set, because those notes use
# backticked kebab-case for workflow values, labels, models, headers, hooks,
# and config keys (issue #3637, PR #3698).
#
# Everywhere else a bare backticked kebab token is a candidate only when this
# set names it; a type claim alone is also enough. The old premise, that every
# backticked kebab token is a skill candidate, holds inside skill and agent
# definition files but fails in prose for exactly the reasons above. Measured
# across `.serena/memories`, `.agents`, `.claude`, and `docs` after PR #3698
# landed: 1485 skill_name findings, of which the overwhelming majority named
# something that has never been a skill in this repository. Closing the
# candidate set brings that to 135 and leaves script_path (687), rule_path
# (73), and instruction_path (17) untouched.
#
# The alternative was appending each offending token to KEBAB_DENYLIST, which
# enumerates the non-skill universe and therefore never terminates. Bounding
# the candidate set by the skill universe instead is small and known. This is
# the same trade #2679 made for single-word tokens.
#
# Cost of the trade: a bare backticked misspelling of a name that was never a
# skill (`` `shipp` ``) no longer produces a finding. Writing the same
# reference with a type claim (`` the `shipp` skill ``) still does, and a type
# claim is what distinguishes a catalog reference from ordinary prose.
#
# Add a name here when a hyphenated skill is retired or renamed, so lingering
# references keep surfacing instead of going silent.
KNOWN_RETIRED_KEBAB_SKILLS: frozenset[str] = frozenset({
    "doc-coverage",
    "doc-sync",
    "github-pr-reply",
    "guard-maturity",
    "session-end",
    "session-init",
    "session-log-fixer",
    "session-migration",
    "session-qa-eligibility",
    "using-forgetful-memory",
})


# Single-word (no-hyphen) skill names the validator treats as skill-reference
# candidates. SKILL_REF_RE requires a hyphen, so single-word skills are
# invisible to it; a backticked single word is otherwise indistinguishable from
# ordinary prose (`memory`, `review`, `session` are all common English words).
# The scanner resolves a single-word backticked token as a skill reference only
# when it is either present in the live `.claude/skills/` catalog OR named here.
# This second arm is what catches a deleted single-word skill: once the
# directory is gone the token is no longer in the catalog, but a stale prose
# reference must still be flagged (issue #2679; observed retiring `incoherence`,
# #2662). Add a name here when a single-word skill is retired or renamed so
# lingering references surface as orphan findings instead of going silent.
#
# Membership in this set is NOT sufficient to flag: a name listed here that
# still resolves to a live catalog directory is a valid reference and produces
# no finding (same resolution path as a hyphenated skill name). The set only
# widens *detection*; the catalog still decides *validity*.
KNOWN_SINGLE_WORD_SKILLS: frozenset[str] = frozenset({
    # Retired / renamed single-word skills. Keep entries until every scanned
    # surface (specs, evals, plugin manifests) has dropped the backticked ref.
    "incoherence",  # DEPRECATED 2026-05-29, absorbed by doc-accuracy; retired #2662
})


METASYNTACTIC_PLACEHOLDERS: frozenset[str] = frozenset({
    # Conventional placeholder names used while documenting scanner syntax.
    # They remain non-candidates even when nearby prose says "skill" because
    # `Skill: `x`` describes the route grammar, not a real skill reference.
    "x", "y", "foo", "bar", "baz", "name",
})
def is_known_retired_kebab_skill(token: str) -> bool:
    """Return True if a hyphenated token names a retired or renamed skill.

    Membership makes the token a reference *candidate*; it does not make it a
    finding. A name listed here that still resolves in the live catalog is a
    valid reference and produces nothing, exactly as with
    ``is_known_single_word_skill``.
    """
    return token in KNOWN_RETIRED_KEBAB_SKILLS


# Skills that live in another repository's catalog and are referenced here on
# purpose. A reference to one of these is correct prose, not an orphan: the
# named skill exists, just not at ``.claude/skills/``. Before this set the
# scanner reported them as critical findings whose offered remedies (update
# the reference, restore the skill, remove the mention) were all wrong, since
# the reference was already right and the skill is not ours to restore
# (issue #3728).
#
# Bounded on purpose, same trade as ``KNOWN_RETIRED_KEBAB_SKILLS``: naming the
# few foreign skills this repository cites is small and known, while deciding
# foreignness by heuristic is not. Add a name here only with the owning
# catalog recorded beside it, so a later reader can check the claim.
FOREIGN_SKILL_CATALOGS: dict[str, str] = {
    "claim-verification-before-ingest": "gstack",
    "front-gate-before-pipeline": "gstack",
}

# Compiled once from the constant catalog names above rather than assembled per
# call. Two reasons, in order of weight. First, it keeps the interpolation away
# from the ``search`` call: Semgrep's LDAP-injection rule keys on a call named
# ``search`` receiving a formatted string and cannot tell ``re.search`` from an
# LDAP client's ``search``, so an inline ``re.search(rf"...")`` here produces a
# blocking review finding for a sink this repository does not have (it declares
# no LDAP dependency and imports no LDAP module). Suppressing that finding is
# not available: the ``security-suppressions-push`` gate in
# ``scripts/validation/git_hook_policy.py`` rejects any newly added suppression
# comment. Second, the pattern set is fixed at import time, so compiling per
# call was wasted work.
_CATALOG_QUALIFIER_PATTERNS: dict[str, re.Pattern[str]] = {
    catalog: re.compile(rf"\b{re.escape(catalog)}\b", re.IGNORECASE)
    for catalog in sorted(set(FOREIGN_SKILL_CATALOGS.values()))
}


def foreign_skill_catalog(token: str) -> str | None:
    """Return the owning catalog when a token names a known foreign skill."""
    return FOREIGN_SKILL_CATALOGS.get(token)


def is_qualified_foreign_skill(token: str, line: str) -> bool:
    """Return True when ``line`` names the catalog that owns ``token``.

    The token alone is not evidence. Issue #3728 asks for the exemption to
    hold only for a catalog-qualified reference, so that an unqualified
    mention of a skill this repository does not ship is still reported. The
    qualifier is the owning catalog name appearing on the same line, which is
    how the prose reads in practice: ``gstack `front-gate-before-pipeline` skill``.
    """
    catalog = FOREIGN_SKILL_CATALOGS.get(token)
    if not catalog:
        return False
    return _CATALOG_QUALIFIER_PATTERNS[catalog].search(line) is not None


def is_known_single_word_skill(token: str) -> bool:
    """Return True if a single-word token is a curated known skill name.

    Used by the scanner to decide whether a backticked single word that is
    absent from the live catalog should be flagged as an orphan skill
    reference. Tokens not in this set and not in the live catalog are treated
    as ordinary prose and ignored, keeping false positives at zero.
    """
    return token in KNOWN_SINGLE_WORD_SKILLS


def is_metasyntactic_placeholder(token: str) -> bool:
    """Return True if token is conventional example syntax, not a skill ref."""
    return len(token) == 1 or token in METASYNTACTIC_PLACEHOLDERS


def is_known_kebab_word(token: str) -> bool:
    """Return True if a kebab-case token is a known non-skill reference.

    Two arms remain: a token with no hyphen is not the kebab shape this
    filter guards, and a model identifier (``claude-opus-5``) is a version
    string that a frontmatter scan can otherwise read as a catalog name.

    The curated denylist that used to sit here was deleted in issue #3726.
    PR #3698 replaced denying non-skills with requiring a type claim or a
    retired-skill allowlist entry before a bare token becomes a candidate at
    all, and recorded why: enumerating the non-skill universe never
    terminates. That migration left the denylist behind. Measured across the
    full corpus, 98 of its 101 entries suppressed nothing, and the survivors
    only suppressed tokens inside this scanner's own test source. A token
    like ``read-only`` is now reachable only when prose calls it a skill,
    and a sentence that calls ``read-only`` a skill is wrong whether or not
    a denylist hides it.
    """
    if "-" not in token:
        return True
    return bool(MODEL_ID_RE.match(token))
