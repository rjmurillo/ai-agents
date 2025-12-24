# Automation Priorities (December 2025)

**Created**: 2025-12-23
**Context**: User feedback on taking a wide-angle lens to identify high-impact automation

> "How we spend our days, is of course, how we spend our lives." - Annie Dillard

## The Problem: Task Saturation

With 115+ memories, countless skills scattered across files, and manual session protocols, agents hit task saturation. The "brain" receives more than it can handle. Automation should serve as extra memory when our own has had enough.

## Priority Areas (High-Impact Workflows)

### P0: Session Initialization (Blocking Gate)

**Current State**: Manual, frequently forgotten, causes rework

**Pain Points**:
- Agents skip Serena initialization → lose project memories
- Agents skip HANDOFF.md → repeat completed work
- Session logs created late or never → lose context

**Automation Opportunity**: Pre-flight automation that refuses to proceed until initialization completes. Not a checklist to remember, but a gate that enforces.

**Impact**: Every session. Prevents the most common failure mode.

---

### P0: Memory Retrieval (Smart Routing)

**Current State**: 115 memories, no index, agents read randomly or skip entirely

**Pain Points**:
- Too many memories to read them all
- No way to know which are relevant without reading them
- Redundant information across memories
- Stale memories mixed with current

**Automation Opportunity**: Memory index/catalog with:
- Topic tags and relevance scores
- "Read these N memories for task X" recommendations
- Staleness detection and cleanup prompts
- Consolidation of overlapping memories

**Impact**: Every session. Reduces cognitive load, improves context retrieval.

---

### P1: Artifact Quality Gate (Self-Containment Validator)

**Current State**: Manual review, Skill-007 not enforced

**Pain Points**:
- Artifacts created with implicit knowledge
- Session logs missing end state, next action
- PRDs missing acceptance criteria
- Operational prompts missing sustainability guidance

**Automation Opportunity**: Validator that checks artifacts against Skill-007:
- [ ] Amnesia test: Would a naive agent succeed?
- [ ] Implicit knowledge: What's missing?
- [ ] For shared resources: Rate limit awareness?

**Impact**: Every artifact handoff. Prevents rework from incomplete context.

---

### P1: Skill Consolidation (Deduplication)

**Current State**: 115 memories with overlapping skills, scattered patterns

**Pain Points**:
- Same skill documented in multiple places
- Conflicting guidance across memories
- No single source of truth per topic
- Skills discovered but not applied

**Automation Opportunity**: Skill catalog that:
- Indexes all skills by topic
- Detects duplicates and conflicts
- Suggests consolidation
- Tracks application frequency

**Impact**: Reduces memory bloat, improves skill discovery.

---

### P2: PR Status Synthesis

**Current State**: Manual `gh pr list`, manual CI check, manual review comment scan

**Pain Points**:
- Takes 5+ API calls to understand one PR
- Easy to miss blocked PRs
- No prioritization of what needs attention

**Automation Opportunity**: Daily/triggered PR dashboard:
- All open PRs with status
- CI failures highlighted
- Review comments needing response
- Merge conflicts flagged
- Rate limit impact noted

**Impact**: PR maintenance efficiency. Batch operations.

---

### P2: Centralized Rate Limit Service

**Current State**: Per-workflow rate limit checks (inconsistent)

**Pain Points**:
- Each workflow implements its own check
- No coordination between workflows
- Autonomous processes can exhaust limits for CI

**Automation Opportunity**: Shared rate limit service:
- Single check before any API-heavy operation
- Coordination between consumers
- Automatic throttling/queuing
- Alerting when approaching limits

**Impact**: System stability. Prevents cascade failures.

---

## The Wide-Angle View

| Category | # Memories | Consolidation Opportunity |
|----------|-----------|---------------------------|
| skills-* | 30+ | Consolidate into skill catalog |
| skill-* | 40+ | Merge with skills-* by topic |
| retrospective-* | 5 | Keep as historical record |
| pattern-* | 8 | Merge into relevant skills |
| research-* | 3 | Archive or integrate findings |
| user-preference-* | 4 | Consolidate into single file |

## Next Actions

1. **Immediate**: Create memory index (list of memories with 1-line summaries)
2. **This week**: Consolidate user preferences into single memory
3. **This month**: Build skill catalog with deduplication
4. **Ongoing**: Apply Skill-007 to all new artifacts

## Measuring Success

- Session initialization failures: Target 0%
- Memory retrieval time: < 30 seconds to find relevant context
- Artifact rework rate: < 10% due to missing context
- Memory count: Plateau then decrease through consolidation
