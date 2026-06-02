# Diagnosis, Actions, and Persistence

Phase 2 (Diagnosis), Phase 3 (Decide What to Do), Phase 4 (Atomicity Scoring and tagging),
Root Cause Pattern Management, and the Memory Protocol. The rubrics below are lifted verbatim
from the canonical source agent body at `.claude/agents/retrospective.md` (the original
Phase 2, Phase 3, Phase 4, "Root Cause Pattern Management", and "Memory Protocol" sections).
Keep them byte-for-byte; the SKILL.md orchestration links to the headings here.

---

## Diagnosis

Prioritize findings for action.

### Diagnostic Priority Order

1. **Critical Error Patterns** - Failures that blocked progress
2. **Success Analysis** - Strategies that contributed to outcomes
3. **Near Misses** - Things that almost failed but recovered
4. **Efficiency Opportunities** - Ways to do same thing better
5. **Skill Gaps** - Missing capabilities identified
6. **Traceability Health** - Spec layer coherence metrics

### Traceability Metrics

When the session involves specification artifacts (requirements, designs, tasks), evaluate spec layer health:

**Run validation:**

```powershell
pwsh scripts/Validate-Traceability.ps1 
```

**Metrics to capture:**

| Metric | Description | Target |
|--------|-------------|--------|
| Valid Chains | Complete REQ -> DESIGN -> TASK traces | 100% of designs |
| Orphaned REQs | Requirements with no implementing design | 0 |
| Orphaned Designs | Designs with no implementing tasks | 0 |
| Broken References | References to non-existent specs | 0 |
| Untraced Tasks | Tasks without design reference | 0 |

**Template:**

````markdown
## Traceability Health

### Current State

| Metric | Count | Status |
|--------|-------|--------|
| Requirements | [N] | - |
| Designs | [N] | - |
| Tasks | [N] | - |
| Valid Chains | [N] | [PASS/WARN/FAIL] |
| Errors | [N] | [PASS/FAIL] |
| Warnings | [N] | [PASS/WARN] |

### Issues Found

#### Errors (Blocking)
- [List broken references, untraced tasks]

#### Warnings (Non-Blocking)
- [List orphaned specs]

### Remediation Actions

| Issue | Fix | Owner |
|-------|-----|-------|
| [Issue] | [Action] | [spec-generator/milestone-planner] |
````

**Integration with Learning Extraction:**

Traceability failures are skill gaps. Extract learnings:

- If broken reference: "Verify spec IDs exist before adding to related field"
- If orphaned REQ: "Create design specs when requirements are approved"
- If untraced task: "Add related field to task front matter during creation"

### Diagnosis Template

````markdown
## Diagnostic Analysis

### Outcome
[Success | Partial Success | Failure]

### What Happened
[Concrete description of actual execution]

### Root Cause Analysis
- **If Success**: What strategies contributed?
- **If Failure**: Where exactly did it fail? Why?

### Evidence
[Specific tools, steps, error messages, metrics]

### Priority Classification
| Finding | Priority | Category | Evidence |
|---------|----------|----------|----------|
| [Finding] | P0/P1/P2 | [Critical/Success/NearMiss/Efficiency/Gap] | [Ref] |
````

---

## Activity: Action Classification

Adapted from Keep/Drop/Add. Categorize what to do with findings.

| Category | Agent Action | Criteria |
|----------|--------------|----------|
| **Keep** | TAG as helpful, increase validation count | Worked, should continue |
| **Drop** | REMOVE or TAG as harmful | Failed, should stop |
| **Add** | ADD new skill | Novel learning, no existing pattern |
| **Modify** | UPDATE existing skill | Refinement to existing pattern |

**Template:**

````markdown
## Action Classification

### Keep (TAG as helpful)
| Finding | Skill ID | Validation Count |
|---------|----------|------------------|
| [Finding] | [Skill-XXX] | [N+1] |

### Drop (REMOVE or TAG as harmful)
| Finding | Skill ID | Reason |
|---------|----------|--------|
| [Finding] | [Skill-XXX] | [Why removing] |

### Add (New skill)
| Finding | Proposed Skill ID | Statement |
|---------|-------------------|-----------|
| [Finding] | [Skill-Category-NNN] | [Atomic statement] |

### Modify (UPDATE existing)
| Finding | Skill ID | Current | Proposed |
|---------|----------|---------|----------|
| [Finding] | [Skill-XXX] | [Current text] | [New text] |
````

## Activity: SMART Validation

Validate every learning before storage. Reinforces atomicity.

| Criterion | Skill Requirement | Check |
|-----------|-------------------|-------|
| **Specific** | One atomic concept, no compound statements | No "and", "also" |
| **Measurable** | Has evidence, can be validated | Has execution reference |
| **Attainable** | Within agent capability | Technically feasible |
| **Relevant** | Applies to actual execution scenarios | Has trigger condition |
| **Timely** | Clear when to apply | Has context/timing |

**Validation Template:**

````markdown
## SMART Validation

### Proposed Skill
**Statement:** [The skill text]

### Validation
| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y/N | [One concept or multiple?] |
| Measurable | Y/N | [Can we verify it worked?] |
| Attainable | Y/N | [Is this technically possible?] |
| Relevant | Y/N | [Does it apply to real scenarios?] |
| Timely | Y/N | [Is trigger condition clear?] |

### Result
- [ ] All criteria pass: Accept skill
- [ ] Some criteria fail: Refine skill
- [ ] Multiple criteria fail: Reject skill
````

## Dependency Ordering

Order actions based on dependencies.

**Template:**

````markdown
## Action Sequence

| Order | Action | Depends On | Blocks |
|-------|--------|------------|--------|
| 1 | [First action] | None | [Actions 2, 3] |
| 2 | [Second action] | [Action 1] | [Action 4] |
| 3 | [Third action] | [Action 1] | None |
````

---

## Atomicity Scoring

All learnings scored 0-100%.

| Factor | Adjustment |
|--------|------------|
| Compound statements ("and", "also") | -15% each |
| Vague terms ("generally", "sometimes") | -20% each |
| Length > 15 words | -5% per extra word |
| Missing metrics/evidence | -25% |
| No actionable guidance | -30% |

### Quality Thresholds

| Score | Quality | Action |
|-------|---------|--------|
| 95-100% | Excellent | Add to skillbook |
| 70-94% | Good | Add with refinement |
| 40-69% | Needs Work | Refine before adding |
| <40% | Rejected | Too vague |

### Examples

**Bad (35%)**: "The caching strategy was effective"

- Vague "effective" (-20%)
- No specifics (-25%)
- Not actionable (-30%)

**Good (92%)**: "Redis cache with 5-min TTL reduced API calls by 73% for user profiles"

- Specific tool (Redis)
- Exact config (5-min TTL)
- Measurable outcome (73%)
- Clear context (user profiles)

### Evidence-Based Tagging

| Tag | Meaning | Evidence Required |
|-----|---------|-------------------|
| **helpful** | Contributed to success | Specific positive execution |
| **harmful** | Caused failure | Specific negative execution |
| **neutral** | No measurable impact | Use without effect |

---

## Root Cause Pattern Management

After Five Whys analysis identifies root causes, systematically store patterns for future prevention.

### Root Cause Categories

Standard categories based on common failure modes:

| Category | Description | Examples |
|----------|-------------|----------|
| **Cross-Cutting Concerns** | Issues affecting multiple components | Missing input validation, inconsistent error handling |
| **Fail-Safe Design** | Missing defensive patterns | No fallbacks, unhandled edge cases |
| **Test-Implementation Drift** | Tests don't match actual behavior | Mocks diverge from reality, stale fixtures |
| **Premature Validation** | Validating before data is complete | Checking state too early, race conditions |
| **Context Loss** | Information not preserved | Missing handoff data, dropped session state |
| **Skill Gap** | Missing capability | No existing pattern for scenario |

### Memory Storage Pattern

Store root cause entities for future pattern matching:

**Create root cause memory:**

```text
mcp__serena__write_memory
memory_file_name: "rootcause-{category}-{nnn}"
content: "# Root Cause: {Category} #{NNN}\n\n**Description**: [What failed and why]\n**Frequency**: [How often this occurs]\n**Impact**: [Severity when it occurs]\n**Detection**: [How to identify this pattern]\n**Prevention**: [How to avoid it]\n**Source**: [PR/Issue/Session reference]\n\n## Related\n- Prevention skill: [skill-file-name]\n- Incident: [incident-ref]\n- Category: [category-name]"
```

### Failure Prevention Matrix

Maintain cumulative statistics across sessions:

````markdown
## Failure Prevention Matrix

| Root Cause Category | Incidents | Prevention Skills | Last Occurrence | Trend |
|---------------------|-----------|-------------------|-----------------|-------|
| Cross-Cutting Concerns | [N] | Skill-Val-001, Skill-Val-002 | [PR/Session ref] | [Up/Down/Stable] |
| Fail-Safe Design | [N] | Skill-Safe-001 | [PR/Session ref] | [Up/Down/Stable] |
| Test-Implementation Drift | [N] | Skill-Test-001 | [PR/Session ref] | [Up/Down/Stable] |
| Premature Validation | [N] | Skill-Val-003 | [PR/Session ref] | [Up/Down/Stable] |
| Context Loss | [N] | Skill-Ctx-001 | [PR/Session ref] | [Up/Down/Stable] |
| Skill Gap | [N] | [New skills added] | [PR/Session ref] | [Up/Down/Stable] |
````

### Root Cause Pattern Template

Add to retrospective artifact when Five Whys identifies root cause:

````markdown
## Root Cause Pattern

**Pattern ID**: RootCause-{Category}-{NNN}
**Category**: [Cross-Cutting | Fail-Safe | Test-Implementation Drift | Premature | Context | Skill-Gap]

### Description
[What failed and why - from Five Whys analysis]

### Detection Signals
- [Signal 1]: How to recognize this pattern early
- [Signal 2]: Warning signs before failure

### Prevention Skill
**Skill ID**: Skill-{Category}-{NNN}
**Statement**: [Atomic prevention strategy]
**Application**: [When and how to apply]

### Evidence
- **Incident**: [PR/Issue/Session reference]
- **Root Cause Path**: [Five Whys chain summary]
- **Resolution**: [What fixed it]

### Relations
- **Prevents by**: [Prevention skill ID]
- **Similar to**: [Related root cause patterns]
- **Supersedes**: [Older patterns this replaces]
````

---

## Memory Protocol

Use Memory Router for search and Serena tools for persistence (ADR-037):

**Search for existing patterns (before creating new):**

```bash
uv run python .claude/skills/memory/scripts/search_memory.py --query "{domain} {description} skill patterns"
```

**Create new skills:**

```text
mcp__serena__write_memory
memory_file_name: "{domain}-{description}"
content: "# Skill: {Description}\n\n**Statement**: [Skill statement with context and evidence]\n\n**Evidence**: [Source reference]\n\n## Details\n\n..."
```

**Update existing skills (add observations):**

```text
mcp__serena__edit_memory
memory_file_name: "[skill-file-name]"
content: "[Updated content with new observation appended]"
```

> **Fallback**: If Memory Router unavailable, read `.serena/memories/` directly with Read tool.

**Deduplication Query:**

```bash
uv run python .claude/skills/memory/scripts/search_memory.py --query "rootcause {Category} {Keywords from description}"
```

If similar pattern exists (>70% similarity), UPDATE existing entity instead of creating new one.
