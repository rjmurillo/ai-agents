# Engineering Knowledge Agent Integration Patterns

## Context

Session 819 integrated 67 engineering knowledge memories across 5 experience tiers into agents and skills. This memory captures reusable patterns for enriching agents with strategic frameworks.

## Integration Patterns

### Pattern 1: Strategic Knowledge Sections

Add "Strategic Knowledge Available" sections to decision-making agents (analyst, architect, planner, high-level-advisor, implementer).

**Structure**:
```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**[Category]** (Primary):
- `memory-name`: One-line use case
- `memory-name`: One-line use case

**[Category]** (Secondary):
- `memory-name`: One-line use case
```

**Benefits**:
- Reduces context switching (agents know what's available)
- Enables proactive framework application
- Makes knowledge immediately accessible during reasoning

**Example**: `.claude/agents/analyst.md` lines 42-62

### Pattern 2: Embedded Framework Guidance

For frequently used frameworks, embed concise guidance directly in agent prompts rather than requiring memory queries.

**When to Embed**:
- Framework applies to >50% of agent tasks
- Quick-reference table fits in <40 lines
- Framework is tier-appropriate for agent role

**Structure**:
```markdown
## [Framework Name] ([Use Case])

[1-2 sentence overview]

| Column | Column | Column |
|--------|--------|--------|
| Value  | Value  | Value  |

**Application**: [When/how to use this]
```

**Benefits**:
- Zero-latency access to critical frameworks
- Consistent application across sessions
- Reduces memory query overhead

**Examples**:
- Cynefin Framework in analyst.md (lines 100-138)
- Chesterton's Fence in architect.md (lines 355-406)
- OODA Loop in high-level-advisor.md

### Pattern 3: Tiered Framework Access

Match framework complexity to agent experience tier:

| Agent | Experience Tier | Framework Tier | Examples |
|-------|----------------|----------------|----------|
| implementer | Junior/Mid | Foundational (Tier 1-2) | SOLID, DRY, Boy Scout Rule |
| architect | Senior/Staff | Staff+ (Tier 3-4) | Chesterton's Fence, Path Dependence |
| high-level-advisor | Principal+ | Distinguished (Tier 4-5) | OODA Loop, Wardley Mapping |
| analyst | All tiers | Progressive disclosure | Cynefin for all, Wardley for strategic |

**Rationale**: Prevents cognitive overload, ensures frameworks match decision scope.

### Pattern 4: Template Integration

Add framework checklists to templates (ADRs, PRDs, retrospectives).

**Structure**:
```markdown
## [Framework Name] Assessment

- [ ] Checkpoint 1: [What to verify]
- [ ] Checkpoint 2: [What to verify]
- [ ] Assessment: [PASS | FAIL | N/A]
```

**Benefits**:
- Forces systematic framework application
- Creates audit trail of strategic thinking
- Prevents framework knowledge from being passive

**Examples**:
- ADR template with Chesterton's Fence checklist (architect.md line 269-273)
- adr-review skill Phase 4 strategic validation (lines 105-153)

### Pattern 5: Skill Enhancement

Enrich existing skills with decision frameworks to improve output quality.

**High-Impact Targets**:
- **decision-critic**: Add Inversion Thinking for failure mode analysis
- **programming-advisor**: Add Core vs Context + Lindy Effect for build-vs-buy
- **adr-review**: Add strategic validation phase with principal-level frameworks

**Pattern**:
1. Identify decision point in skill workflow
2. Select tier-appropriate framework
3. Add as explicit step with checklist
4. Update frontmatter description to mention framework

**Example**: programming-advisor gained 107 lines of Core vs Context + hidden costs analysis

## Implementation Strategy

### Phase 1: Critical Enhancements (P0)
- Strategic analysis frameworks for analyst (Cynefin, Wardley, Rumsfeld)
- Principal-level patterns for architect (Chesterton's Fence, Path Dependence)
- Legacy modernization patterns for architect (Strangler Fig, Expand/Contract)
- Decision quality improvements (Inversion Thinking in decision-critic)
- Knowledge infrastructure (engineering-knowledge-index.md)

### Phase 2: High Priority (P1)
- Strategic decision cycles (OODA Loop in high-level-advisor)
- Planning frameworks (Three Horizons, Critical Path in planner)
- Technology evaluation (Lindy Effect in analyst)
- Build vs buy analysis (Core vs Context in programming-advisor)
- ADR validation (strategic review in adr-review)

### Phase 3: Future Enhancements (P2)
- Orchestrator routing improvements
- Push-pr workflow enhancements
- Remaining agent enrichments

## Validation Approach

### Analyst Phase
Before implementation, use analyst agent to:
1. Review all engineering knowledge commits
2. Identify high-impact integration opportunities
3. Generate prioritized recommendations (P0/P1/P2)
4. Provide implementation guidance for each item

**Benefit**: Structured analysis prevents ad-hoc decisions, ensures comprehensive coverage.

### Two-Phase Commits
Separate critical (P0) from high-priority (P1) into distinct commits:
- P0: Must-have strategic frameworks
- P1: High-value enhancements
- P2: Nice-to-have improvements (defer)

**Benefit**: Enables focused review, allows partial adoption if needed.

## Script Path Conventions (Session 820)

When documenting script invocations in SKILL.md files, always use full paths from repository root:

**WRONG**:
```bash
python3 scripts/decision-critic.py
```

**CORRECT**:
```bash
python3 .claude/skills/decision-critic/scripts/decision-critic.py
```

**Rationale**: 
- Relative paths like `scripts/` are ambiguous (which scripts directory?)
- Reviewer tools (rg, grep) may search from different working directories
- Full paths work regardless of where the skill is invoked from
- Prevents false positives in PR reviews about missing scripts

**Evidence**: PR #863 comment thread PRRT_kwDOQoWRls5o0UQS - reviewer's `rg --files -g "decision-critic.py"` failed to find script despite it existing in repo because documentation used relative path.

## Cross-References

- **Engineering Knowledge Index**: [engineering-knowledge-index](engineering-knowledge-index.md)
- **Session 819**: Engineering knowledge integration session (2026-01-10)
- **ADR-007**: Memory-first architecture (foundation for this pattern)

## Related Memories

- `memory-first-pattern`: Why memory retrieval precedes implementation
- `agent-workflow-patterns`: How agents collaborate
- [skills-standards-reconciled](skills-standards-reconciled.md): Skill frontmatter requirements
- `session-protocol`: Session start/end requirements
