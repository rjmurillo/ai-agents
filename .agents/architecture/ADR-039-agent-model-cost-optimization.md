---
id: ADR-039
status: deprecated
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-039: Agent Model Cost Optimization

## Status

Deprecated (2026-08-25). The provisional window below closed without
validation, and the changes it made were reverted.

### How the provisional window actually ended (recorded 2026-08-25)

The original status is retained verbatim below. This section records what
happened to it, because for seven months the record said "provisional pending
validation" for a window that had already expired.

**Zero of the four Final Acceptance Criteria were ever measured.** The criteria
listed below call for monitoring data on error rates, missed security issues,
architecture-decision quality, and user satisfaction.
`.agents/governance/model-pin-evidence.json`, the sidecar that would hold such
evidence, contains `"pins": []`. No validation verdict, pass or fail, was ever
recorded anywhere.

**The downgrades were reverted, but not through this ADR's rollback
procedure.** The per-agent rollback documented in this record's Implementation
section was never executed. The assignments were reverted incidentally on
2026-02-07, three weeks after the window closed, as a side effect of commit
`568af6775` (PR #1046, "migrate agent prompts from cloudmcp-manager to Memory
Router (ADR-037)"), which rewrote 41 agent prompt files for an unrelated reason.
That commit does not mention ADR-039 at all. Verified against the live tree: the
six agents this ADR downgraded all read `model: opus` today, which is ADR-002's
assignment.

**`supersedes` is `[]`, deliberately.** This ADR claims to supersede ADR-002
"pending validation". The validation never happened and the assignments were
undone, so the supersession never took effect. Recording it in the frontmatter
would assert a relationship that does not hold. ADR-002 is deprecated in the same
change, on its own separate grounds.

**Why `deprecated` and not `rejected`.** This repository uses `rejected` for a
proposal declined before it was ever in force: ADR-095 ("Recorded so the proposal
is findable and does not return") and ADR-061 (withdrawn before acceptance). That
is not this record. ADR-039's changes were implemented and ran in production for
roughly five weeks, from 2026-01-03 until the incidental revert. `deprecated`
means "was in force, no longer is", which is what happened here. `implemented` is
`true` for the same reason, and it stays true despite the revert: the field gates
amend-versus-supersede, and a decision whose code shipped must not be silently
amended even after that code is gone.

### Original status (2026-01-03), retained

**PROVISIONAL** (2026-01-03 to 2026-01-17)

**Supersedes**: ADR-002 (pending validation)

**Provisional Rationale**: This ADR documents model optimization changes already implemented in Session 128 (commits 651205a, d81f237, f101c06). Independent-thinker review (rating: 3/10) identified that empirical quality testing was not conducted before implementation. Two-week provisional period allows monitoring to validate that downgraded agents maintain acceptable quality.

**Final Acceptance Criteria**:
- No increase in agent error rates during 2-week period
- No security issues missed by downgraded security agent
- No architecture decisions requiring Opus-level reasoning that Sonnet cannot handle
- User satisfaction maintained (no quality complaints)
- Monitoring data collected and analyzed

**If Validation Fails**: Revert specific agents to Opus using procedures in Implementation Notes (lines 157-196)

## Date

2026-01-03

## Context

ADR-002 assigned 7 agents to Opus 4.5 based on theoretical reasoning requirements. Review of 289 cumulative session logs (December 17, 2025 to January 3, 2026) during Session 128 suggested that most Opus agents perform structured tasks that cheaper models can handle.

**Note**: This ADR documents changes implemented before formal analysis. Session 128 was implementation-focused, not analytical. The provisional period provides empirical validation that should have preceded implementation.

### Claude 4.5 Family Pricing

| Model | Input | Output | vs Sonnet |
|-------|-------|--------|-----------|
| Opus 4.5 | $5/MTok | $25/MTok | 1.67x |
| Sonnet 4.5 | $3/MTok | $15/MTok | 1.0x (baseline) |
| Haiku 4.5 | $1/MTok | $5/MTok | 0.33x |

Every agent invocation using Opus costs 1.67x more per token than Sonnet. Using Opus for tasks that Sonnet can handle wastes money on each API call.

### Problem

Five agents on Opus 4.5 perform tasks that fit Sonnet 4.5 capabilities:
- **orchestrator**: Task routing follows structured logic
- **architect**: Design review applies patterns and checklists
- **independent-thinker**: Critical analysis without code generation
- **roadmap**: Strategic planning produces structured text
- **high-level-advisor**: Strategic guidance follows domain knowledge patterns

Two agents on Sonnet 4.5 perform high-volume operations that fit Haiku 4.5:
- **memory**: Context retrieval and storage (CRUD operations)
- **skillbook**: Pattern matching for skill management (lookup tasks)

## Decision

Optimize agent assignments within the Claude 4.5 family using a three-tier strategy:

### Three-Tier Assignment Model

| Tier | Use Case | Cost vs Sonnet |
|------|----------|----------------|
| **Opus 4.5** | Code generation requiring highest reasoning | 1.67x |
| **Sonnet 4.5** | Analysis, design review, coordination, strategic planning | 1.0x |
| **Haiku 4.5** | High-volume CRUD, pattern matching, retrieval | 0.33x |

### Final Distribution

| Model | Count | Agents |
|-------|-------|--------|
| Opus 4.5 | 2 | implementer, security |
| Sonnet 4.5 | 15 | orchestrator, architect, analyst, planner, critic, qa, devops, explainer, task-generator, retrospective, pr-comment-responder, spec-generator, independent-thinker, roadmap, high-level-advisor |
| Haiku 4.5 | 3 | memory, skillbook, context-retrieval |

### Changes from ADR-002

**Downgrade to Sonnet 4.5 (5 agents):**
- orchestrator (opus → sonnet, commit d81f237)
- architect (opus → sonnet, commit d81f237)
- independent-thinker (opus → sonnet, commit 651205a)
- roadmap (opus → sonnet, commit 651205a)
- high-level-advisor (opus → sonnet, commit f101c06)

**Retain Opus 4.5 (reverted):**
- security (reverted from d81f237 downgrade per adr-review debate - asymmetric risk)

**Downgrade to Haiku 4.5 (2 agents):**
- memory (sonnet → haiku, commit 651205a)
- skillbook (sonnet → haiku, commit 651205a)

### Unchanged from ADR-002

**Retain Opus 4.5 (2 agents):**
- implementer: Code generation requires highest reasoning
- security: Reverted per adr-review debate (high-level-advisor: asymmetric risk - security bugs are invisible during validation)

## Rationale

### Why Downgrade to Sonnet 4.5?

The six downgraded agents perform structured analysis that does not require Opus 4.5 level reasoning:

- **Design review** (architect): Applies architectural patterns and checklists
- **Security review** (security): Applies OWASP guidelines and threat modeling frameworks
- **Task routing** (orchestrator): Follows structured logic to select agents
- **Strategic planning** (roadmap, high-level-advisor): Produces structured text with clear formats
- **Critical analysis** (independent-thinker): Provides feedback without code generation

These tasks benefit from strong reasoning but do not require the deepest capabilities that code generation demands. Using Opus 4.5 costs 67% more per token than Sonnet 4.5.

### Why Keep Implementer on Opus 4.5?

Code generation has high error cost. Production code bugs create security issues, technical debt, and rework. The implementer needs the highest reasoning to minimize these risks.

### Why Downgrade to Haiku 4.5?

Memory retrieval and skillbook pattern matching are CRUD and lookup operations. These tasks do not require reasoning. Haiku 4.5 provides faster response (1-3s vs 3-15s) at 66.67% lower cost.

## Alternatives Considered

### Option 1: Keep ADR-002 Assignments (7 Agents on Opus 4.5)

**Rejected**: Session analysis shows that six Opus agents perform tasks that Sonnet 4.5 can handle. Design review, security review, and strategic planning apply frameworks rather than requiring deepest reasoning. Paying 1.67x more per token wastes budget.

### Option 2: Downgrade All Agents to Sonnet 4.5

**Rejected**: Code generation quality matters. Production code bugs create security issues and technical debt. Keeping implementer on Opus 4.5 maintains quality for highest-stakes work.

### Option 3: Dynamic Model Selection Per Task

**Rejected**: Adds routing complexity and unpredictable costs. Agent usage patterns are stable. Static assignments are simpler to maintain and debug.

### Option 4: Keep Strategic Agents on Opus 4.5

**Rejected**: If Sonnet 4.5 can handle the work quality, using Opus 4.5 wastes money. Session data shows strategic agents perform structured analysis that fits Sonnet capabilities.

## Consequences

### Positive

- **POS-001**: Reduced API costs (66.67% savings on 6 downgraded agents vs Opus 4.5)
- **POS-002**: Faster memory operations (Haiku 4.5: 1-3s vs Sonnet 4.5: 3-15s)
- **POS-003**: Data-driven assignments (289-290 sessions analyzed)
- **POS-004**: Clear three-tier assignment criteria
- **POS-005**: Opus 4.5 reserved for highest-stakes work (code generation)

### Negative

- **NEG-001**: Security review quality risk mitigated by keeping security agent on Opus 4.5 (per adr-review debate).
- **NEG-002**: Orchestration quality risk (complex routing may degrade)
- **NEG-003**: Architecture review quality risk (ADR quality may suffer)
- **NEG-004**: Haiku 4.5 limits reasoning (complex queries need escalation)
- **NEG-005**: Monitoring burden (track quality metrics for 2-week provisional period)
- **NEG-006**: Reversion complexity (6 agents need rollback procedures)

## Implementation Notes

### Files Changed

**Commit 651205a** (memory, skillbook, independent-thinker, roadmap):
- `.claude/agents/memory.md`: sonnet → haiku
- `.claude/agents/skillbook.md`: sonnet → haiku
- `.claude/agents/independent-thinker.md`: opus → sonnet
- `.claude/agents/roadmap.md`: opus → sonnet

**Commit d81f237** (orchestrator, architect, security):
- `.claude/agents/orchestrator.md`: opus → sonnet
- `.claude/agents/architect.md`: opus → sonnet
- `.claude/agents/security.md`: opus → sonnet

**Commit f101c06** (high-level-advisor):
- `.claude/agents/high-level-advisor.md`: opus → sonnet

### Monitoring Plan (2-Week Provisional Period)

**Baseline Metrics** (established 2026-01-03):
- Agent error rate: 0 known errors at start of provisional period
- Security PIV reports: 3 completed reports (PIV-PR60, SR-002, SR-003) as quality reference
- User satisfaction: No complaints as of provisional start

**Metrics to Track**:
1. Agent invocation success rates (target: no increase in failures)
2. User correction counts (target: no increase from baseline)
3. Security PIV quality (target: no missed vulnerabilities vs historical detection rate)
4. Task completion times (target: no significant increase)

**Failure Thresholds** (trigger reversion):
- Any critical security vulnerability missed that pattern matching should have caught
- 2+ user complaints about agent quality degradation
- Measurable increase in task retry rates

**Monitoring Owner**: Session operator reviews weekly during provisional period

### Reversion Procedures

**Per-agent rollback** (if quality degrades):

```bash
# orchestrator
git show d81f237^:.claude/agents/orchestrator.md > .claude/agents/orchestrator.md

# architect
git show d81f237^:.claude/agents/architect.md > .claude/agents/architect.md

# security
git show d81f237^:.claude/agents/security.md > .claude/agents/security.md
```

**Full reversion to ADR-002**:

```bash
git revert f101c06 d81f237 651205a
```

### Success Criteria

- No increase in agent error rates
- Faster memory/skillbook response times
- No user complaints about quality

## Related Decisions

- [ADR-002: Agent Model Selection Optimization](ADR-002-agent-model-selection-optimization.md)
  - The supersession this record originally claimed never took effect, so
    `supersedes` is `[]`. See the 2026-08-25 status resolution above. ADR-002 is
    deprecated on its own separate grounds.
- ADR-007: Memory-First Architecture - Memory agent performance (reference only)

## References

**Session Data**:
- Session 128: `.agents/sessions/2026-01-03-session-128-context-optimization.md`
- Sessions 289-290: December 21, 2025 to January 3, 2026

**Claude 4.5 Family** (all models released 2025):
- Opus 4.5: `claude-opus-4-5-20251101` (Nov 24, 2025)
- Sonnet 4.5: `claude-sonnet-4-5-20250929` (Sept 29, 2025)
- Haiku 4.5: `claude-haiku-4-5-20251001` (Oct 2025)

**Pricing** (per million tokens):
- Opus 4.5: $5 input, $25 output
- Sonnet 4.5: $3 input, $15 output
- Haiku 4.5: $1 input, $5 output

**Documentation**:
- [Claude Model Capabilities](https://docs.anthropic.com/en/docs/about-claude/models)

---

## Agent-Specific Fields

### Agent Names

8 agents affected (see Implementation Notes for full list)

### Overlap Analysis

N/A (configuration changes only, no responsibility changes)

### Entry Criteria

| Scenario | Priority | Confidence |
|----------|----------|------------|
| New agent creation | P0 | High |
| Quarterly usage review | P1 | High |
| Quality regression detected | P0 | High |
| Cost threshold exceeded | P0 | High |

### Explicit Limitations

1. Static assignments (not dynamic per-task)
2. Manual reversion procedures
3. Manual quality monitoring
4. Based on current usage patterns (may change)

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent error rate | No increase | Issue tracking |
| Memory latency | Faster | Response time logs |
| User satisfaction | No degradation | Feedback tracking |

---

*Template Version: 1.0*
*Session: 128*
*Commits: 651205a, d81f237, f101c06*
