# Skill: Multi-Agent ADR Debate Protocol

**Extracted**: 2025-12-23
**Source**: Session 86 - ADR-019 Multi-Agent Debate

## Skill-Debate-001: Structured Multi-Agent ADR Consensus (95%)

**Statement**: Use 4-phase rounds (Independent Review, Consolidation, Resolution, Convergence Check) to achieve ADR consensus in 2-3 rounds

**Context**: When reviewing ADRs that affect multiple domains (architecture, security, implementation)

**Trigger**: ADR requires validation from 3+ specialized perspectives

**Evidence**: ADR-019 achieved consensus in 2 rounds with 5 agents (architect, critic, independent-thinker, security, analyst). All P0 issues resolved before convergence.

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```text
Round N:
  Phase 1: Independent Review
    - Each agent reviews ADR independently
    - Output: Strengths, Weaknesses, Questions, Recommendations, Blocking Concerns, Position
    
  Phase 2: Consolidation
    - Orchestrator collects all feedback
    - Categorize issues: P0 (blocking), P1 (important), P2 (nice-to-have)
    - Identify consensus areas and conflicts
    
  Phase 3: Resolution
    - Update ADR based on P0 and P1 issues
    - Document decisions made and rationale
    
  Phase 4: Convergence Check
    - Re-invoke agents on updated ADR
    - Check for Accept or Disagree-and-Commit
    - If not converged and rounds < 10, continue to next round
```

**Success Criteria**:

- All agents either Accept or Disagree-and-Commit
- Dissent documented in debate log
- ADR updated with all P0 resolutions

## Correlated-Premise Audit (guard against fast unanimous convergence)

**Statement**: Before accepting fast unanimous convergence on a high-stakes ADR, verify the ADR's load-bearing factual claims against primary sources. Fast unanimity is not automatically a strong signal. It can be correlated failure.

**Why**: The 4-phase protocol defends well against groupthink in reasoning. The independent-thinker role challenges assumptions and framing, and Disagree-and-Commit preserves dissent. But every agent reviews the same ADR text. When the ADR itself carries a factual error, all agents inherit it. Independent-thinker challenges the reasoning while accepting the false premise, because the error is in the shared input, not in anyone's logic. This is the ensemble "popularity trap" from Wisdom and Delusion of LLM Ensembles for Code Generation and Repair (arXiv:2510.21513): majority-vote consensus can lock a panel onto a shared error that the best single model would have caught.

**Worked incident (ADR-045, Session 1181, 2026-02-07)**: The ADR stated "no validated external demand" and "single-maintainer project" when it actually targeted about 400 users for organizational distribution. High-Level-Advisor voted Divest-and-Contain on ROI grounds. No agent caught it, because the error was a shared false fact, not bad reasoning. Correcting the context flipped the vote to Accept. See `adr-review-observations.md`.

**Protocol addition**: When Phase 4 reaches unanimous Accept in Round 1 (or Round 2) on an ADR that is high-stakes (irreversible, cross-cutting, or resource-committing), do NOT treat that as convergence. Add one Round: assign one agent (default: independent-thinker, or a fresh reviewer) to verify each load-bearing factual claim in the ADR against a primary source (the spec, the benchmark, the usage data, the actual user count). Only then accept. Signal to watch: a D&C rejection on ROI or scope grounds often means the ADR context is wrong, not that the agent disagrees. Investigate the fact base before re-arguing (see observations, Session 1181).

**Anti-Pattern**:

- Single-agent ADR review (misses domain expertise)
- Endless debate without convergence check (rounds > 10)
- Ignoring dissent (must document Disagree-and-Commit rationale)

**Key Learnings from ADR-019**:

1. **independent-thinker is essential**: Challenges groupthink with evidence-based contrarian views
2. **P0 vs P1 categorization enables progress**: Not all issues are blocking
3. **Disagree-and-Commit is valid consensus**: Documented dissent allows progress
4. **Prerequisites section blocks premature Accepted status**: Use for testable conditions
5. **Scope clarification prevents scope creep**: Explicitly state what ADR does NOT address

---

## Related Documents

- Source: `.agents/sessions/2025-12-23-session-86-adr-017-debate.md`
- ADR: `.agents/architecture/ADR-019-model-routing-low-false-pass.md`
- Debate Log: `.agents/critique/ADR-019-debate-log.md`
- Related: skills-architecture (ADR patterns)
- Related: skills-critique (conflict escalation)
