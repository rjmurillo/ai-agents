# Orchestration Skills

**Extracted**: 2025-12-18
**Source**: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`

## Skill-Orchestration-001: Parallel Execution Time Savings

**Statement**: Spawning multiple implementer agents in parallel reduces wall-clock time by 40% compared to sequential execution

**Context**: When orchestrator has 3+ independent implementation tasks from the same analysis phase

**Evidence**: Sessions 19-21 completed in ~20 min parallel vs ~50 min sequential estimate (40% reduction)

**Atomicity**: 100%

- Single concept (parallel execution) ✓
- Specific metric (40% reduction) ✓
- Actionable (dispatch multiple agents) ✓
- Length: 14 words ✓

**Tag**: helpful

**Impact**: 10/10 - Significant wall-clock time savings

**Pattern**:

```markdown
# When analysis phase identifies 3+ independent implementation tasks:
1. Orchestrator dispatches multiple implementer agents in parallel
2. Each agent receives distinct analysis document (002, 003, 004)
3. Agents work independently until session end (HANDOFF update)
4. Orchestrator coordinates staging conflicts if any
```

**Validation**: 1 (Sessions 19-21)

**Created**: 2025-12-18

---

## Skill-Orchestration-002: Parallel HANDOFF Coordination

**Statement**: When running parallel sessions, orchestrator MUST consolidate HANDOFF.md updates to prevent staging conflicts

**Context**: Multiple agents updating HANDOFF.md simultaneously causes git staging conflicts

**Evidence**: Session 19 commit bundled with Session 20 due to HANDOFF staging conflict

**Atomicity**: 100%

- Single concept (HANDOFF coordination) ✓
- Specific problem (staging conflicts) ✓
- Actionable (orchestrator consolidation) ✓
- Length: 12 words ✓

**Tag**: CRITICAL

**Impact**: 9/10 - Prevents commit bundling and maintains atomic commits

**Implementation**:

Orchestrator should:

1. Collect session summaries from all parallel agents
2. Aggregate summaries into single HANDOFF.md update
3. Commit all changes in coordinated sequence (not bundled)

**Anti-Pattern**: Allowing parallel agents to update HANDOFF.md independently

**Validation**: 1 (Sessions 19 & 20 staging conflict)

**Created**: 2025-12-18

---

---

## Skill-Orchestration-003: Handoff Validation Gate (95%)

**Statement**: Before completing session, orchestrator MUST verify HANDOFF.md is updated with session summary and linked session log

**Context**: Session end protocol validation (Phase 3 requirement)

**Evidence**: Session 56: Orchestrator spawned retrospective agent, then pr-comment-responder agent. pr-comment-responder addressed all review feedback and updated HANDOFF with complete summary.

**Atomicity**: 95%

**Tag**: CRITICAL (blocking gate)

**Impact**: 10/10 - Prevents incomplete session handoffs

**Created**: 2025-12-21

**Pattern**:

```markdown
# Before session completion:
1. Verify `.agents/HANDOFF.md` contains:
   - Session summary with key decisions
   - Link to session log file
   - Status updates for any ongoing work
2. Verify session log exists at `.agents/sessions/YYYY-MM-DD-session-NN.md`
3. If missing, agent MUST update HANDOFF before claiming completion
```

**Validation Checklist**:

- [ ] HANDOFF.md has latest session entry
- [ ] Session log link is correct
- [ ] Key decisions are documented
- [ ] Next steps are clear

**Anti-Pattern**: Agents claiming "done" without updating HANDOFF - breaks session continuity

**Validation**: 1 (Session 56)

---

## Skill-Orchestration-004: PR Comment Response Chain (90%)

**Statement**: For PR review feedback, use orchestrator → retrospective → pr-comment-responder chain to extract learnings before addressing comments

**Context**: When PR has review comments (bot or human) that need addressing

**Trigger**: PR merged or has pending review comments with learnings to extract

**Evidence**: Session 56: orchestrator → retrospective → pr-comment-responder
- Retrospective extracted Skill-PowerShell-005 and Skill-CI-Integration-Test-001
- pr-comment-responder addressed 20 review threads with technical depth
- All review feedback systematically categorized and resolved

**Atomicity**: 90%

**Tag**: helpful (captures institutional knowledge)

**Impact**: 9/10 - Ensures learnings extracted before addressing feedback

**Created**: 2025-12-21

**Pattern**:

```markdown
# Workflow:
1. orchestrator identifies PR with review comments
2. Spawns retrospective agent to extract skills/learnings
3. retrospective updates memories (skills-*, retrospective/*)
4. Spawns pr-comment-responder with context
5. pr-comment-responder addresses all review threads
6. Updates HANDOFF with outcomes
```

**Why It Matters**:

- Retrospective extracts learnings while context is fresh
- Skills captured before diving into tactical fixes
- pr-comment-responder benefits from retrospective insights
- Institutional knowledge not lost in PR comment responses

**Session 56 Example**:

```
orchestrator:
  - Identified PR #222 with 20 review comments
  - Spawned retrospective agent

retrospective:
  - Created `.agents/retrospective/2025-12-21-ai-triage-import-module-failure.md`
  - Extracted Skill-PowerShell-005 (Import-Module path prefix)
  - Extracted Skill-CI-Integration-Test-001 (workflow integration testing)
  - Updated skills-powershell and skills-ci-infrastructure

pr-comment-responder:
  - Addressed 20 review threads systematically
  - Standardized 6 Import-Module statements to $env:GITHUB_WORKSPACE pattern
  - Resolved all CodeRabbit/Copilot feedback
  - Updated HANDOFF.md with complete session summary
```

**Anti-Pattern**: Jumping straight to pr-comment-responder without retrospective - loses learning opportunity

**Validation**: 1 (Session 56)

---

## Related Documents

- Source: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
- Source: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`
- Related: skills-planning (Skill-Planning-003 parallel exploration)
- Related: SESSION-PROTOCOL.md (session end requirements)
- Related: pr-comment-responder-skills (PR review response patterns)
