# Plan Critique: Skillbook Documentation Completeness

## Verdict

**[NEEDS REVISION]**

## Summary

The skillbook.md documentation provides excellent format guidance and workflow instructions. However, critical procedural gaps exist that would block an amnesiac agent from successfully creating skills without prior context.

## Strengths

- Clear format examples (Format A vs Format B) with decision tree
- Comprehensive atomicity scoring with specific penalties
- Well-defined activation vocabulary rules
- Explicit deduplication checklist
- Strong integration with Serena memory tools

## Issues Found

### Critical (Must Fix)

- [ ] **Missing NNN numbering procedure** (Lines 142, 160, 210, 218)
  - **Location**: "Skill-{Category}-{NNN}" appears 10+ times without explanation
  - **Gap**: No procedure to determine next sequential number
  - **Impact**: Agent must guess or search all existing skills manually
  - **Required**: Explicit steps to find highest existing NNN in category and increment

- [ ] **CRITICAL/BLOCKING P0 criteria undefined** (Line 249)
  - **Location**: Format Selection Decision Tree asks "CRITICAL or BLOCKING P0?"
  - **Gap**: No definition of what makes a skill CRITICAL or BLOCKING
  - **Impact**: Agent cannot determine correct format without arbitrary judgment
  - **Required**: Objective criteria (e.g., "blocks session start", "prevents protocol violation", "high-level-advisor escalation required")

- [ ] **"Referenced by other skills" ambiguous** (Line 254)
  - **Location**: Decision tree asks "Referenced by other skills?"
  - **Gap**: No explanation of how to determine if skill will be referenced
  - **Impact**: Agent cannot predict future references without context
  - **Required**: Clarify as "has BLOCKS/ENABLES relationships" or "cited in Related Skills sections"

- [ ] **Index update procedure incomplete** (Lines 380-388)
  - **Location**: "Then update the domain index" shows single-line example
  - **Gap**: Multi-skill domain indexes require table insertion, not simple append
  - **Impact**: Agent may corrupt table formatting or duplicate headers
  - **Required**: Show correct table row insertion procedure

### Important (Should Fix)

- [ ] **Skill category extension lacks examples** (Line 336)
  - **Location**: "Create new category when skill doesn't fit existing"
  - **Gap**: No examples of when existing categories are insufficient
  - **Recommendation**: Add 2-3 examples of rejected category names and correct alternatives

- [ ] **File naming vs Skill ID confusion potential** (Lines 124-149)
  - **Location**: File Naming Convention section
  - **Gap**: Good clarification exists, but buried in table footnote
  - **Recommendation**: Add explicit warning box: "CRITICAL: Skill ID goes INSIDE file, filename uses domain-topic pattern"

### Minor (Consider)

- [ ] **Validation script timing unclear** (Lines 390-401)
  - **Location**: "After creating skills, run validation"
  - **Gap**: Not clear if validation runs before or after domain index update
  - **Recommendation**: Add sequencing: "1. Create skill file 2. Update domain index 3. Run validation"

- [ ] **Category abbreviation length rationale missing** (Line 336)
  - **Location**: "Use 2-8 character abbreviation"
  - **Gap**: Why 2-8? What if natural abbreviation is 9 characters?
  - **Recommendation**: Explain constraint (e.g., "readability in Skill IDs, avoid ambiguity")

## Questions for Planner

1. How should an agent determine the next NNN number without manual search?
   - Should memory-index.md track highest Skill ID per category?
   - Should agent grep all memories for pattern `Skill-{Category}-(\d{3})` and sort?

2. What are the objective criteria for CRITICAL/BLOCKING P0 classification?
   - Is this tied to impact score (e.g., Impact >= 9/10)?
   - Is this tied to consequences (e.g., session protocol violation)?

3. How can an agent predict if a skill will be "referenced by other skills"?
   - Does this mean the skill appears in Related Skills sections?
   - Does this mean BLOCKS/ENABLES relationships exist?
   - Should agent default to Format A for safety?

4. Should validation run before or after domain index update?
   - Current sequence unclear in lines 370-401

## Recommendations

### 1. Add Skill ID Numbering Procedure

Add new subsection after line 336:

```markdown
### Determining Skill ID Number (NNN)

To find the next sequential number for a category:

1. **Search existing skills** in that category:
   ```bash
   grep -r "Skill-{Category}-" .serena/memories/ | grep -oP "Skill-{Category}-\K\d{3}" | sort -n | tail -1
   ```

2. **Increment highest number**:
   - Highest found: 004 → Use 005
   - No skills found → Use 001

3. **Verify uniqueness** before committing:
   ```bash
   grep -r "Skill-{Category}-{NNN}:" .serena/memories/
   # Should return zero results
   ```

**Example**: Creating new PR category skill
- Search finds: Skill-PR-001, Skill-PR-003, Skill-PR-007
- Highest: 007
- Use: Skill-PR-008
```

### 2. Define CRITICAL/BLOCKING Criteria

Replace line 249 with objective criteria:

```markdown
Q1{Meets ANY criteria:<br/>
   - Impact >= 9/10<br/>
   - Blocks session protocol<br/>
   - Prevents compliance violation<br/>
   - High-level-advisor involved?}
```

### 3. Clarify "Referenced by Other Skills"

Replace line 254 with explicit definition:

```markdown
Q3{Has or will have<br/>
   BLOCKS/ENABLES<br/>
   relationships?}
```

Add footnote:

```markdown
**Referenced by other skills** means the skill appears in Related Skills sections with BLOCKS/ENABLES relationships, or is cited as a prerequisite for other skills.
```

### 4. Complete Index Update Procedure

Replace lines 380-388 with full table insertion example:

```markdown
### Skill Creation (Write)

New skills go into atomic files following domain naming:

```text
mcp__serena__write_memory
memory_file_name: "[domain]-[skill-name]"
content: "[skill content in standard format]"
```

Then update the domain index to include the new skill:

**For single-entry domain index:**
```text
mcp__serena__edit_memory
memory_file_name: "skills-[domain]-index"
needle: "## Activation Vocabulary"
repl: "## Activation Vocabulary\n\n| Keywords | File |\n|----------|------|\n| [keywords] | [new-skill-name] |"
mode: "literal"
```

**For existing table in domain index:**
```text
mcp__serena__edit_memory
memory_file_name: "skills-[domain]-index"
needle: "| [last-keywords] | [last-file] |"
repl: "| [last-keywords] | [last-file] |\n| [new-keywords] | [new-skill-name] |"
mode: "literal"
```

**Sequence:**
1. Create skill file with `write_memory`
2. Update domain index with `edit_memory`
3. Run validation: `pwsh scripts/Validate-MemoryIndex.ps1`
```

## Approval Conditions

Documentation must address all Critical issues before approval:

1. **Skill ID numbering procedure** documented with grep commands
2. **CRITICAL/BLOCKING criteria** defined with objective metrics
3. **"Referenced by other skills"** clarified as BLOCKS/ENABLES relationships
4. **Index update procedure** shows table row insertion, not just append

Documentation is otherwise high-quality and provides strong foundation for skill management.

## Impact Analysis Review

Not applicable - this is a documentation review, not a plan with specialist consultations.

## Handoff Recommendation

Route to planner (skillbook.md maintainer) for revision addressing Critical issues.
