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
