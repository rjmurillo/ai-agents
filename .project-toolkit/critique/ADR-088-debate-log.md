# ADR-088 Debate Log: Progressive Disclosure for Book-Derived Rules

## Summary

ADR-088 was reviewed under the adr-review skill. Verdict: accept. The decision moves situational book-derived depth from always-on rules to one on-demand skill while keeping everyday engineering synthesis rules inline.

## Round 1 Reviews

### Architect

Verdict: Accept.

The boundary is coherent. Always-on rules retain every-task behavior. The new `software-engineering-library` skill owns task-specific depth. The ADR names affected generated surfaces and the budget ratchet, so the architecture stays testable.

### Critic

Verdict: Accept.

The main risk is late retrieval. The ADR states that risk and mitigates it with concrete trigger phrases plus retained always-on synthesis. The rejected alternatives cover the likely failure modes: keeping all books inline and fragmenting into eight skills.

### Independent Thinker

Verdict: Accept with reservation.

The move depends on skill triggering quality, which is weaker than passive context. The reservation is acceptable because the moved material is situational. Critical rules remain inline, and the budget gate prevents context creep.

### Security

Verdict: Accept.

The change does not weaken security rules. It moves design and operations depth, not mandatory security controls. References that affect production failure handling still exist under the skill and can be invoked during resilience work.

### Analyst

Verdict: Accept.

The evidence supports the decision. Phase 1 measured about 218 KB for code edits. Phase 2 measurement after the move is about 95 KB for code extensions. The 99 KB ceiling gives 3 KB to 5 KB headroom and locks in the reduction.

### High-Level Advisor

Verdict: Accept.

This is the right trade. Paying 54k tokens for every code edit is not discipline. Keeping the everyday synthesis inline avoids the known indirection failure. The PR should land as a bounded corpus-curation change.

## Convergence

All six roles accept ADR-088. No P0 or P1 blockers remain.

## Required Follow-up

Criterion 3 for issue #3419, full metadata normalization, remains separate scope. This ADR should not absorb it.

## Round 2 Amended Text Review

### Scope

ADR-088 was re-reviewed after the PR added explicit `autoplan` routing, post-investigation `analyze` routing, and replaced the unwired rollback trigger with issue #3589.

### Key Issues Addressed

- Progressive disclosure reachability now has two paths: direct `autoplan` selection and post-investigation `analyze` handoff.
- The rollback trigger no longer claims an unwired gate. Issue #3589 tracks owner, cadence, persisted consecutive-run state, and CI or scheduled invocation.
- The review verified that the eight moved references still exist under `software-engineering-library`.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | The two-gate retrieval design matches the ADR-078 router boundary and the impact table matches the changed surfaces. |
| critic | Disagree-and-Commit | Residual P2 concerns remain: quote the exact budget output, define reachability measurement in #3589, and populate decision-makers before acceptance. |
| independent-thinker | Accept | The ADR names the strongest counterargument, late retrieval, and mitigates it with retained always-on synthesis plus explicit routing. |
| security | Accept | The change moves instructional content between loading mechanisms and adds no tool permission, auth, or data-flow change. |
| analyst | Accept | The implementation matches the ADR claims: budget ratchet, eight references, generated mirrors, and routing paths are present. |
| high-level-advisor | Accept | The trade aligns with ADR-069 by reducing dead context while keeping everyday engineering rules inline. |

### Convergence

All six roles accept or disagree-and-commit. No P0 or P1 blockers remain. ADR-088 can remain proposed in this PR. The acceptance transition should address the P2 notes or link them to their owning issue.

## Round 3 Amendment Review (issue #5951)

### Scope

ADR-088 gains an "Amendment (issue #5951)" section. The always-on
`pragmatic-programmer` rule moves to
`software-engineering-library/references/pragmatic-programmer.md`, and the
Forbidden Patterns blocklist plus the seven-point "Prefer designs that" list move
from `unified-software-engineering.md` to `references/forbidden-patterns.md`.
The code-extension budget ceilings ratchet from 99,000 to 86,000 bytes. ADR-061's
two citations of `.claude/rules/pragmatic-programmer.md` are repointed to the
new reference path so they do not dangle.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | Applies ADR-088's own criterion: situational book depth moves, the every-task tiebreaker stays inline. Impact surfaces (mirrors, ADR-061 citations, scenarios, lossless fixtures) are complete. P2: cite where the 12,000-byte floor comes from. |
| critic | Disagree-and-Commit | P0: the seven-point "Prefer designs that" list was deleted rather than relocated. P1: with the blocklist on demand, no always-on text forbids outbound calls without timeouts or nested retries. |
| independent-thinker | Accept with reservation | The "model already knows this" premise matches the context-optimizer admission test, but byte savings do not prove retrieval. Reachability should be measured after merge. |

### Key Issues Addressed

- Critic P0: the seven-point list now lives in `references/forbidden-patterns.md`
  under Primary Directive, and the amendment text records the relocation.
- Critic P1: the trimmed always-on rule names the highest-risk production
  patterns inline (no explicit timeout, nested or non-idempotent retries,
  unbounded queues) and points to the full reference.
- Architect P2: the amendment cites issue #5951 as the source of the
  12,000-byte floor and records the 86 KB ceiling ratchet.
- Independent-thinker reservation: `pragmatic-programmer` and
  `forbidden-patterns` join `MOVED_REFERENCE_IDS` in the weekly activation
  gate, so the existing consecutive-failure rollback alert covers them. The
  R1-R8 recovery-contract scenarios move to `universal.json` because that
  contract lives in always-on `universal.md`.

### Convergence

All three roles accept or disagree-and-commit after the fixes above. No P0 or
P1 blockers remain. ADR-088 stays proposed, and ADR-061 needs only the citation
repoint.
