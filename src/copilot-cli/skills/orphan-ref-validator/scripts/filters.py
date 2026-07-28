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


# Retired or renamed hyphenated skill names, the kebab counterpart of
# KNOWN_SINGLE_WORD_SKILLS above and governed by the same contract: the set
# widens detection, the live catalog still decides validity.
#
# Why the kebab path needs it too. Every backticked kebab token used to be a
# skill candidate on its own. That premise holds inside skill and agent
# definition files, where kebab-case overwhelmingly does name a skill. It
# fails in prose, where kebab-case is the ordinary spelling for Actions
# runners, model ids, HTTP headers, config keys, hook lifecycle names, and
# repository topics. Measured on `.serena/memories/`: 183 findings across 122
# distinct tokens, and not one of those tokens has ever been a skill in this
# repository (issue #3637). Repo-wide the open premise produced 1790 findings
# of which 1700 named something that was never a skill.
#
# The old remedy was appending each offending token to KEBAB_DENYLIST, which
# enumerates the non-skill universe and therefore never terminates. Closing
# the candidate set instead bounds the problem by the skill universe, which is
# small and known. This is the same trade #2679 made for single-word tokens.
#
# Cost of the trade: a bare backticked misspelling of a name that was never a
# skill (`` `shipp` ``) no longer produces a finding. Writing the same
# reference with a type claim (`` the `shipp` skill ``) still does, and a type
# claim is what distinguishes a catalog reference from ordinary prose.
#
# Add a name here when a hyphenated skill is retired or renamed, so lingering
# references keep surfacing instead of going silent.
KNOWN_KEBAB_SKILLS: frozenset[str] = frozenset({
    "doc-coverage",           # retired, absorbed by doc-accuracy
    "doc-sync",               # retired, absorbed by doc-accuracy
    "github-pr-reply",        # retired, absorbed by pr-comment-responder
    "session-migration",      # retired
    "session-qa-eligibility",  # retired
})


def is_known_kebab_skill(token: str) -> bool:
    """Return True if a kebab token names a retired or renamed skill.

    Membership makes the token a reference *candidate*; it does not make it a
    finding. A name listed here that still resolves in the live catalog is a
    valid reference and produces nothing, exactly as with
    ``is_known_single_word_skill``.
    """
    return token in KNOWN_KEBAB_SKILLS


def is_known_single_word_skill(token: str) -> bool:
    """Return True if a single-word token is a curated known skill name.

    Used by the scanner to decide whether a backticked single word that is
    absent from the live catalog should be flagged as an orphan skill
    reference. Tokens not in this set and not in the live catalog are treated
    as ordinary prose and ignored, keeping false positives at zero.
    """
    return token in KNOWN_SINGLE_WORD_SKILLS


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
