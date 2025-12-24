# Documentation: Self-Contained Artifacts

## Skill-Documentation-006: Self-Contained Operational Prompts

**Statement**: Include all resource constraints, failure modes, shared resource context, and dynamic adjustment rules for autonomous agents.

**Context**: Prompts intended for standalone Claude instances or autonomous agents.

**Evidence**: PR #301 - Rate limit guidance missing from autonomous-pr-monitor.md.

**Atomicity**: 88% | **Impact**: 9/10 | **Tag**: operational

**Required Sections**:
1. **Resource Constraints**: API limits, shared resources, budget targets
2. **Failure Modes**: Detection and recovery for each failure type
3. **Dynamic Adjustments**: Condition → Action rules
4. **Shared Context**: What else uses these resources
5. **Stop Conditions**: When to self-terminate

## Skill-Documentation-007: Self-Contained Artifacts (General)

**Statement**: Any artifact consumed by a future agent MUST be self-contained enough for that agent to succeed without implicit knowledge.

**Context**: Session logs, handoff artifacts, PRDs, task breakdowns, planning documents.

**Atomicity**: 95% | **Impact**: 10/10 | **Tag**: critical (foundational)

**Universal Validation Questions**:
1. "If I had amnesia and only had this document, could I succeed?"
2. "What do I know that the next agent won't?"
3. "What implicit decisions am I making that should be explicit?"

**Artifact-Specific Extensions**:

| Artifact Type | Additional Questions |
|---------------|---------------------|
| Session Logs | End state? Blocked? Next action? |
| Handoff Artifacts | Decisions made? What was rejected? |
| PRDs | Acceptance criteria unambiguous? |
| Task Breakdowns | Tasks atomic? Dependencies explicit? |
| Operational Prompts | See Skill-Documentation-006 |
