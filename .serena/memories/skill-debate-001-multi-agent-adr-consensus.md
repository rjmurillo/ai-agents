# Skill: Multi-Agent ADR Debate Protocol

**Extracted**: 2025-12-23
**Source**: Session 86 - ADR-017 Multi-Agent Debate

## Skill-Debate-001: Structured Multi-Agent ADR Consensus (95%)

**Statement**: Use 4-phase rounds (Independent Review, Consolidation, Resolution, Convergence Check) to achieve ADR consensus in 2-3 rounds

**Context**: When reviewing ADRs that affect multiple domains (architecture, security, implementation)

**Trigger**: ADR requires validation from 3+ specialized perspectives

**Evidence**: ADR-017 achieved consensus in 2 rounds with 5 agents (architect, critic, independent-thinker, security, analyst). All P0 issues resolved before convergence.

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

**Anti-Pattern**:
- Single-agent ADR review (misses domain expertise)
- Endless debate without convergence check (rounds > 10)
- Ignoring dissent (must document Disagree-and-Commit rationale)

**Key Learnings from ADR-017**:

1. **independent-thinker is essential**: Challenges groupthink with evidence-based contrarian views
2. **P0 vs P1 categorization enables progress**: Not all issues are blocking
3. **Disagree-and-Commit is valid consensus**: Documented dissent allows progress
4. **Prerequisites section blocks premature Accepted status**: Use for testable conditions
5. **Scope clarification prevents scope creep**: Explicitly state what ADR does NOT address

---

## Related Documents

- Source: `.agents/sessions/2025-12-23-session-86-adr-017-debate.md`
- ADR: `.agents/architecture/ADR-017-model-routing-low-false-pass.md`
- Debate Log: `.agents/architecture/ADR-017-debate-log.md`
- Related: skills-architecture (ADR patterns)
- Related: skills-critique (conflict escalation)
