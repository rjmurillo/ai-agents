# Orchestration Skills

**Created**: 2025-12-18
**Updated**: 2025-12-23 (consolidated from 3 atomic memories)
**Sources**: Various retrospectives and parallel execution sessions
**Skills**: 4

---

## Skill-Orchestration-001: Parallel Execution Time Savings

**Statement**: Parallel agent dispatch reduces wall-clock time by 30-50% for independent tasks

**Context**: Multiple independent implementation tasks can proceed simultaneously

**Evidence**: Sessions 19-21: Parallel completed in ~20 min vs ~50 min sequential (40% reduction)

**Atomicity**: 100% | **Impact**: 10/10 | **Tag**: helpful

**Good Candidates**:
- Multiple analysis tasks on independent topics
- Implementation of separate, non-conflicting features
- Research/exploration of different approaches

**Poor Candidates**:
- Tasks with dependencies (A must complete before B)
- Tasks modifying same files (staging conflicts)
- Tasks requiring sequential context

**Time Calculation**:

```text
Sequential: Task1 + Task2 + Task3 = 51 min
Parallel: max(Task1, Task2, Task3) + coordination = 20 min
Savings: 61% reduction
```

**Coordination Overhead**: Expect 10-20% (dispatch, conflict resolution, HANDOFF aggregation)

---

## Skill-Orchestration-002: Parallel HANDOFF Coordination

**Statement**: Parallel sessions updating HANDOFF.md require orchestrator coordination to prevent commit bundling

**Context**: Multiple agents in parallel that will update HANDOFF.md at session end

**Evidence**: Sessions 19 & 20: Concurrent HANDOFF updates caused staging conflict (commit 1856a59 bundled)

**Atomicity**: 100% | **Impact**: 9/10 | **Tag**: CRITICAL

**Problem**: SESSION-PROTOCOL requires HANDOFF update. Parallel agents create staging conflicts.

**Solution - Orchestrator Aggregation**:

1. **Parallel agents skip HANDOFF.md** - note in session log: "SKIP (orchestrator aggregates)"
2. **Orchestrator collects summaries** after all parallel sessions complete
3. **Single HANDOFF update** with all summaries

```markdown
## Recent Work

### 2025-12-18: Parallel Implementation (Sessions 19-21)

- Session 19: Created PROJECT-CONSTRAINTS.md per Analysis 002
- Session 20: Added Phase 1.5 BLOCKING gate per Analysis 003
- Session 21: Created Check-SkillExists.ps1 per Analysis 004
```

**Overhead**: Orchestrator aggregation < 5 minutes

---

## Skill-Orchestration-003: Handoff Validation Gate

**Statement**: Orchestrator MUST validate Session End checklist before accepting agent handoff

**Context**: Before orchestrator accepts handoff from specialized agent

**Evidence**: Mass failure (2025-12-20): 23 of 24 agents handed off without Session End checklist complete

**Atomicity**: 92% | **Impact**: 10/10 | **Tag**: CRITICAL

**Acceptance Criteria**:

1. Session log exists at `.agents/sessions/YYYY-MM-DD-session-NN.md`
2. `Validate-SessionEnd.ps1` passes (exit code 0)
3. Agent provides validation evidence in handoff output

**Rejection Response**:

```markdown
❌ **Handoff Rejected**: Session End checklist incomplete

**Validation**: FAIL - 3 unchecked requirements
  - [ ] HANDOFF.md update
  - [ ] Markdown lint
  - [ ] Commit changes

**Required action**: Complete checklist, then re-handoff.
```

**Acceptance Response**:

```markdown
✅ **Handoff Accepted**: Session End protocol compliant

**Validation**: PASS - All requirements complete
**Commit SHA**: 3b6559d
```

---

## Skill-Orchestration-004: PR Comment Response Chain

**Statement**: For PR review feedback, use orchestrator → retrospective → pr-comment-responder chain

**Context**: PR has review comments (bot or human) that need addressing

**Evidence**: Session 56: Chain extracted Skill-PowerShell-005 before addressing 20 review threads

**Atomicity**: 90% | **Impact**: 9/10 | **Tag**: helpful

**Workflow**:

```text
1. orchestrator identifies PR with review comments
2. Spawns retrospective agent → extracts skills/learnings
3. retrospective updates memories (skills-*, retrospective/*)
4. Spawns pr-comment-responder with context
5. pr-comment-responder addresses all review threads
6. Updates HANDOFF with outcomes
```

**Why This Order**: Retrospective extracts learnings while context is fresh. Skills captured before tactical fixes. Institutional knowledge preserved.

**Anti-Pattern**: Jumping straight to pr-comment-responder - loses learning opportunity.

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| 001 | 3+ independent tasks - dispatch in parallel |
| 002 | Parallel sessions - orchestrator aggregates HANDOFF |
| 003 | Agent handoff - validate before accepting |
| 004 | PR comments - retrospective → responder chain |

## Related

- skills-planning (Skill-Planning-003 parallel exploration)
- SESSION-PROTOCOL.md (session end requirements)
- skills-pr-review (PR review response patterns)
