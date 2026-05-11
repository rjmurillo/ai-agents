---
type: requirement
id: REQ-011
title: Agent-Skill Classification Audit (Phase 1 of issue #2003)
status: draft
priority: P1
category: functional
epic: GH-1944
source: GH-2003
related:
  - DESIGN-011
  - ADR-030
  - ADR-036
created: 2026-05-10
updated: 2026-05-10
author: spec
tags:
  - catalog-consolidation
  - agents
  - audit
  - discriminator
---

# REQ-011: Agent-Skill Classification Audit (Phase 1 of issue #2003)

## Source

GitHub issue rjmurillo/ai-agents#2003 (parent epic #1944). PRD at `.agents/specs/PRD-agent-skill-classification-audit.md`.

## Requirement Statement

WHEN the maintainer requests an agent-skill classification audit for the 23 agents in `.claude/agents/`
THE SYSTEM SHALL produce a deterministic per-agent verdict (skill / context-fork-skill / keep-as-agent / merge-into-X) by scoring each agent against the four discriminator criteria from issue #2003 plus a fifth frontmatter-bytes load-budget criterion, with one-line evidence citations on every score, committed at `.agents/audits/YYYY-MM-DD-agent-skill-classification-audit.md` AND linked from a comment on issue #2003
SO THAT misclassified agents are identified and queued for Phase 2 refactor without expanding scope into the refactor work itself, and the load-budget impact of recommended migrations is quantified against the catalog truncation pressure observed in current Claude Code sessions.

## Acceptance Criteria

(EARS-format; each independently pass/fail testable. Numbering matches PRD §8 AC-1..AC-12.)

- [ ] **AC-1**: WHEN the audit is run THE SYSTEM SHALL produce a markdown file at `.agents/audits/YYYY-MM-DD-agent-skill-classification-audit.md` SO THAT the table is durable, version-controlled, and reviewable in a PR.
- [ ] **AC-2**: WHEN the audit is run THE SYSTEM SHALL post or update a comment on issue #2003 that links to the committed file SO THAT the issue's first acceptance criterion is satisfied without duplicating the table inline.
- [ ] **AC-3**: THE SYSTEM SHALL include exactly one row per file matching `.claude/agents/*.md` excluding `AGENTS.md` and `CLAUDE.md` SO THAT no agent is skipped or double-counted (expected: 23 rows on 2026-05-10).
- [ ] **AC-4**: WHEN any row's c1, c2, c3, c4, or c5 columns are populated THE SYSTEM SHALL include a one-line evidence citation in the corresponding `*_evidence` column SO THAT the verdict is auditable, not assertional.
- [ ] **AC-5**: THE SYSTEM SHALL set `verdict = skill` when `discriminator_score >= 2` AND no `keep-as-agent` exception is documented in `verdict_rationale` SO THAT the rule from issue #2003 ("Anything scoring 2+ Yes is a candidate") is applied deterministically.
- [ ] **AC-6**: THE SYSTEM SHALL set `verdict = keep-as-agent` when the agent body documents a context-isolation requirement that cannot be satisfied by `context: fork` SO THAT genuine separate-context agents (`orchestrator`, `analyst`, `critic`, `pr-comment-responder` per the issue's counter-signal section) are correctly preserved.
- [ ] **AC-7**: THE SYSTEM SHALL include a `has_shared_template` column populated by checking for `templates/agents/{agent}.shared.md` per ADR-036 SO THAT Phase 2 refactor planning correctly targets dual-source agents.
- [ ] **AC-8**: THE SYSTEM SHALL include a per-row `c5_frontmatter_bytes` measurement (bytes from start of file to end of YAML frontmatter delimiter) SO THAT load-budget impact of `verdict = skill` recommendations is quantified.
- [ ] **AC-9**: THE SYSTEM SHALL include a summary footer with: total agents, count by verdict, total `c5_frontmatter_bytes` saved if all `verdict = skill` rows were migrated, and citations to ADR-030, ADR-036, and `.agents/governance/agent-consolidation-process.md` SO THAT readers see authority and impact at a glance.
- [ ] **AC-10**: THE SYSTEM SHALL produce a Phase 2 backlog list (one bullet per `verdict ≠ keep-as-agent` row, with one-line justification) committed alongside the audit table SO THAT the issue's second acceptance criterion is satisfied.
- [ ] **AC-11**: THE SYSTEM SHALL record a verdict for every row SO THAT the issue's third acceptance criterion is satisfied; "no decision" is not a valid verdict.
- [ ] **AC-12**: WHEN the Phase 3 CI check is referenced THE SYSTEM SHALL link to a separate filed GitHub issue (not implement the check) SO THAT the issue's fourth acceptance criterion is satisfied without expanding this audit's scope.

## Non-Functional Requirements

- **NFR-1 (Determinism, scoped)**: Two runs of the audit on the same git SHA SHALL produce byte-identical output for c1, c3, c4, c5, and `has_shared_template` columns. **c2 is human-judgment and MAY vary between reviewers** (see PRD §11 c2 count rule). Verdict can change for borderline agents whose discriminator_score depends on c2; this is an explicit limitation of the count rule, not a determinism failure. Reviewers may rebalance individual c2 scores.
- **NFR-2 (Read-only)**: The audit SHALL NOT modify any file under `.claude/agents/`, `templates/agents/`, or `src/`.
- **NFR-3 (Auditable)**: Every assertion in the audit SHALL cite a file path, line number, PR number, or git SHA in its evidence column.
- **NFR-4 (Bounded effort)**: Audit execution SHALL complete in less than 6 hours of human reviewer time per Q4 wedge.

## Dependencies

- ADR-030 (skills-pattern-superiority), discriminator authority
- ADR-036 (two-source agent template architecture), `has_shared_template` column source
- `.agents/governance/agent-consolidation-process.md`, process the audit applies and extends
- `.agents/governance/spec-schemas.md`, schema for this REQ/DESIGN/TASK trio
- Issue #2003, source of acceptance criteria
- Epic #1944, parent

## Out of Scope

See PRD §9. Briefly: Phase 2 refactors (separate issues), Phase 3 CI check (separate issue), 24th caveman agent, downstream platform variants, eval infrastructure, SKILL-CREATION-CRITERIA amendments.
