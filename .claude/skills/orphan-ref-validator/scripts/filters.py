#!/usr/bin/env python3
"""Curated filter sets for orphan-ref-validator.

Houses the denylist of kebab-case tokens that match ``SKILL_REF_RE`` but
are not skill references in the working tree (model identifiers, schema
fields, third-party Action names, bot identifiers, etc.). Kept in a
separate module so ``scan.py`` stays under the 500-line file-size lint
cap.
"""

from __future__ import annotations

import re

MODEL_ID_RE = re.compile(r"^claude-(opus|sonnet|haiku)-\d")

KEBAB_DENYLIST: frozenset[str] = frozenset({
    # Prose hyphenated phrases
    "well-known", "open-source", "self-contained", "follow-up",
    "kebab-case", "snake-case", "ad-hoc", "real-time", "in-place",
    "out-of-scope", "in-scope", "end-to-end", "best-practice", "copy-paste",
    "spec-pipeline",
    "left-hand", "right-hand", "ai-agents", "claude-code", "case-by-case",
    "long-running", "short-running", "non-empty", "non-zero", "non-null",
    "pass-through", "high-level", "low-level", "high-leverage",
    "round-trip", "step-by-step", "fall-through", "cross-cutting",
    "fix-loop", "read-only", "write-only", "first-principles",
    "first-class", "second-class", "third-party", "drop-in", "in-flight",
    "in-progress", "build-time", "run-time", "compile-time",
    # YAML frontmatter / Claude Code skill schema field names
    "allowed-tools", "argument-hint", "size-exception",
    "disable-model-invocation", "user-invocable",
    # Third-party Actions / scanners / CodeQL configs
    "codeql-action", "security-extended", "security-and-quality",
    "github-script", "actions-checkout", "actions-cache",
    # Bot / role / actor identifiers
    "rjmurillo-bot", "copilot-swe-agent", "gemini-code-assist",
    "agent-controlled", "mention-triggered", "review-bot",
    "code-review-bot",
    # ADR-058 / INTERVIEW-1854 eval verdict + CVE-source literals
    "keep-as-audit", "halt-due-to-flakiness", "keep-and-improve",
    "public-cve", "paraphrased-from-public", "synthetic-novel",
    "description-validation-bypass",
    # REQ-011 / DESIGN-011 agent-vs-skill classification verdict literals.
    # Same family as `keep-as-audit` above: REQ-011 AC-6 reads "THE SYSTEM
    # SHALL set `verdict = keep-as-agent`", and TASK-011 TAC-4 counts
    # `context-fork-skill` verdicts. Both name an enum value, not a skill.
    "keep-as-agent", "context-fork-skill",
    # Spec section-template names. REQ-012 proposes adding a
    # `co-change-checklist` section template to `.claude/commands/spec.md`;
    # the token names a template heading, not a skill directory.
    "co-change-checklist",
    # PowerShell / npm / pip module names that appear as backticked refs
    "powershell-yaml", "python-frontmatter",
    # Section anchors / API category labels
    "graphql-vs-rest", "graphql-pr-operations",
    "github-cli-api-patterns", "github-rest-api-reference",
    # Distributed-systems vocabulary
    "eventually-consistent", "strongly-consistent",
    # Voice-rule glossary and validation vocabulary that are terms, not skills.
    "fan-in", "fan-out", "get-library-docs", "tree-shaking",
    "vendor-portability", "zero-copy",
    # Git hook lifecycle names
    "pre-commit", "pre-push", "commit-msg", "post-commit",
    "pre-receive", "post-receive", "pre-rebase",
    # Plugin namespace identifiers (forthcoming + existing entries).
    # `project-toolkit` is the actual plugin name in `.claude-plugin/marketplace.json`
    # and `.github/plugin/marketplace.json`; backticked spec mentions of it (e.g. in
    # INTERVIEW-review-axes-convergence) match SKILL_REF_RE and would false-positive
    # without this entry. Refs PR #1979 round 18 (Devin filters.py:57).
    "claude-toolkit", "copilot-cli-toolkit",
    "claude-agents", "copilot-cli-agents",
    "project-toolkit",
    # CI job / workflow names referenced in spec content. `drift-check` is the
    # planned ai-pr-quality-gate.yml job from REQ-008/TASK-008; backticked
    # references describe a CI job, not a `.claude/skills/drift-check/`. Refs
    # PR #1979 round 18 (Copilot REQ-008/TASK-008 forward refs).
    "drift-check",
})


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
    "session-migration",
    "session-qa-eligibility",
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

    Filters tokens that match the SKILL_REF_RE pattern but should not be
    flagged as orphan skill references: prose phrases, model identifiers,
    third-party Action and config names, frontmatter field labels, bot
    identifiers, and eval verdict literals seen in ADRs.
    """
    if "-" not in token:
        return True
    if MODEL_ID_RE.match(token):
        return True
    return token in KEBAB_DENYLIST
