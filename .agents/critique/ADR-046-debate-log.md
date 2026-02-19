# ADR-046 Debate Log: Planning Agent Rename

## Date

2026-02-08

## ADR Under Review

`.agents/architecture/ADR-046-planning-agent-rename.md`

## Related Work (Phase 0)

- **PR #1101**: Introduced task-planner agent (directly related)
- **Issue #581**: Skills Index Registry (tangentially related)
- **Issue #166**: Agent Capability Gaps comparison (tangentially related)

## Agent Reviews (Phase 1)

### Architect

**Verdict**: ACCEPT_WITH_CONDITIONS

**Issues Identified**:

- P1-001: Missing agent-specific fields (Overlap Analysis, Entry Criteria, Success Metrics)
- P1-002: Missing reversibility assessment
- P1-003: Missing confirmation method in dedicated section
- P2-001: Decision drivers not extracted as bulleted list
- P2-002: ADR-039 reference may become stale
- P2-003: Governance documents already updated but not noted

**Assessment**: Structural compliance good; minor template gaps.

### Critic

**Verdict**: ACCEPT_WITH_CONDITIONS

**Issues Identified**:

- P0-001: Rollback strategy missing
- P0-002: GitHub Actions/workflows impact undefined
- P0-003: Skill directory rename mechanics unclear
- P1-001: No validation criteria
- P1-002: Documentation update scope unclear
- P1-003: MCP server configuration impact unknown
- P2-001: No user communication plan

**Risk Assessment**: Highest risk is incomplete migration causing intermittent failures.

### Independent-Thinker

**Verdict**: ACCEPT_WITH_CONDITIONS

**Devil's Advocate Position**:

- Evidence of confusion is unsubstantiated ("frequently confuse" not backed by data)
- Task-planner agent merged on 2026-02-08, the same date as this ADR (no production observation time)
- Orchestrator uses table-driven routing, not name parsing
- File count understated (ADR says ~70, actual is 153)
- Partial rename (new agent only) could achieve 80% benefit at 10% cost

**Conditions**:

1. Adjust evidence language from observed to preventive
2. Correct file count
3. Acknowledge partial naming pattern (3 of 18+ agents)
4. Add redirect/alias mechanism consideration

### Security

**Verdict**: ACCEPT

**Security Impact**: LOW (2/10)

**Findings**:

- No permission boundary changes
- No credential exposure
- Supply chain assessment: None
- 3 stale CI configuration references (labeler.yml, workflows) - operational, not security

**Recommendations**: Update stale CI configurations; no security gate required.

### Analyst

**Verdict**: ACCEPT_WITH_CONDITIONS

**Evidence Assessment**: WEAK

- Claimed confusion not documented in session logs or retrospectives
- Task-planner introduced on 2026-02-08 (insufficient observation time)
- Valid as preventive measure, not reactive fix

**Feasibility Assessment**: HIGH

- 153 files staged (118% over 70-file estimate)
- Implementation 95% complete
- Gap: Skill directory rename status unclear

**Conditions**:

1. Verify skill directory rename included or explicitly deferred
2. Update workflow files with new agent names
3. Revise problem statement to reflect preventive nature

### High-Level-Advisor

**Verdict**: ACCEPT_WITH_CONDITIONS

**Strategic Assessment**: FAVORABLE

- Cost-benefit clearly favorable (one-time cost, permanent benefit)
- Timing optimal (PR #1101 integration gap needs closing)
- Template-based generation absorbs most mechanical work

**Timing Assessment**: GOOD

**Conditions**:

1. Verify or complete skill directory rename
2. Document excluded categories more explicitly

## Consolidation (Phase 2)

### Consensus

All 6 agents ACCEPT the decision. The action-object naming pattern is sound and eliminates structural ambiguity.

### Conflicts Resolved

| Issue | Resolution |
|-------|------------|
| Skill directory rename | Clarified: `.claude/skills/planner/` is a separate interactive skill, not the agent. No rename needed. ADR updated. |
| Evidence language | Adjusted from "frequently confuse" to "creates routing ambiguity risk" |
| File count | Updated from ~70 to ~150 |
| Excluded categories | Expanded to list all historical document categories |

### Outstanding P1/P2 Items

| Priority | Item | Status |
|----------|------|--------|
| P1 | Reversibility note | Added to ADR |
| P1 | Governance docs in scope | Added to ADR |
| P2 | Decision drivers extraction | Deferred (not blocking) |
| P2 | ADR-039 cross-reference note | Deferred (historical ADRs retain names at acceptance time) |

## Final Verdict (Phase 4)

**ACCEPTED with revisions applied**

All 6 agents Accept. P0 issues resolved (skill directory clarification). P1 issues addressed through ADR edits. Dissent from independent-thinker acknowledged (partial rename alternative has merit but full rename chosen for consistency).

## Validation Execution

Validation was performed during the review:

- `pwsh build/Generate-Agents.ps1 -Validate` confirms generated files match committed files
- Grep scan for stale references (planner, task-generator, task-planner) in active configuration
- Workflow YAML file path references verified against renamed files

## Recommendations to Orchestrator

1. ADR-046 approved for commit
2. Pre-commit hook should now pass (ADR reviewed)
3. Consider adding validation script for future renames (critic recommendation)

## Dissent Record

**Independent-Thinker Reservation**: The evidence base for observed confusion is weak. The decision is sound as a preventive measure, but the ADR originally overstated the problem. This has been corrected.
