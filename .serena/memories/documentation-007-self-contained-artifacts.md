# Skill-Documentation-007: Self-Contained Artifacts (General)

**Statement**: Any artifact consumed by a future agent MUST be self-contained enough for that agent to succeed without implicit knowledge.

**Context**: Session logs, handoff artifacts, PRDs, task breakdowns, planning documents.

**Atomicity**: 95% | **Impact**: 10/10 | **Tag**: critical (foundational)

**Universal Validation Questions**:

1. "If I had amnesia and only had this document, could I succeed?"
2. "What do I know that the next agent won't?"
3. "What implicit decisions am I making that should be explicit?"

**Artifact-Specific Extensions**:

| Artifact Type | Additional Questions |
|---------------|----------------------|
| Session Logs | End state? Blocked? Next action? |
| Handoff Artifacts | Decisions made? What was rejected? |
| PRDs | Acceptance criteria unambiguous? |
| Task Breakdowns | Tasks atomic? Dependencies explicit? |
| Operational Prompts | See Skill-Documentation-006 |

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
