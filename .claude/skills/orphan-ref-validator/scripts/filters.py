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
    # PowerShell / npm / pip module names that appear as backticked refs
    "powershell-yaml", "python-frontmatter",
    # Section anchors / API category labels
    "graphql-vs-rest", "graphql-pr-operations",
    "github-cli-api-patterns", "github-rest-api-reference",
    # Distributed-systems vocabulary
    "eventually-consistent", "strongly-consistent",
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
