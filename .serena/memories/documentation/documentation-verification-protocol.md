# Skill-Documentation-008: Amnesiac-Proof Documentation Verification

**Statement**: Verify agent documentation with critic before commit using amnesiac execution test.

**Context**: After updating agent documentation (*.md files in src/claude/, templates/agents/, AGENTS.md, or .agents/agents/)

**Evidence**: Session 2025-12-23 (Issue #307) - Critic verification caught 4 gaps in skillbook.md and 5 gaps in memory.md before commit. All [FAIL] items converted to [PASS] with objective fixes.

**Atomicity**: 98% | **Impact**: 10/10

**Tags**: #P0, #BLOCKING (for documentation quality)

## Pattern

Before committing agent documentation, run this 5-step protocol:

### Step 1: Self-Review

Ask: "What would an amnesiac agent NOT know from this documentation?"

List specific gaps (file naming, numbering, decision criteria, etc.)

### Step 2: Invoke Critic

```python
Task(
    subagent_type="critic",
    prompt="""Review [file] for completeness. An amnesiac agent will read ONLY this file.

    Can they:
    1. [Specific capability question 1]
    2. [Specific capability question 2]
    3. [...]

    Report [PASS]/[FAIL] for each with objective gap identification."""
)
```

### Step 3: Fix All [FAIL] Items

For each [FAIL], apply objective fixes:

| Gap Type | Fix Pattern |
|----------|-------------|
| Undefined criteria | Add decision tree with explicit branches |
| Missing procedure | Add numbered steps with actual commands |
| Vague terms | Replace with quantified thresholds or mapping tables |
| Ambiguous references | Add grep commands or file path examples |

**Required fix quality**:

- NOT "when appropriate" → INSTEAD "when X > threshold Y"
- NOT "similar to" → INSTEAD "grep command: `grep -r 'pattern' path/`"
- NOT "as needed" → INSTEAD "if condition A then action B, else action C"

### Step 4: Re-Run Critic

Invoke critic again with same questions. Repeat Step 3 until all [PASS].

### Step 5: Commit With Verification Evidence

Include in commit message:

```
[PASS] Critic verification: all amnesiac execution tests

Verified: [list of capability questions]
```

## Anti-Pattern

**NEVER**:

- Commit documentation without critic verification
- Accept vague terms ("when appropriate", "as needed", "similar to")
- Assume prior context will be available to future agents

**Example of vague (REJECT)**:
> "Choose the appropriate index for your skill"

**Example of objective (ACCEPT)**:
> "Match skill keywords to memory-index.md Task Keywords column. If >50% overlap exists, use that domain's index. If <50% overlap AND 5+ skills expected, create new domain index. Else use closest related domain."

## Related

- **ENABLES**: Skill-Documentation-007 (provides HOW to achieve self-containment principle)
- **ENABLES**: All agent documentation updates
- **REFERENCES**: Skill-Quality-002 (QA routing pattern, critic-as-gate)

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
