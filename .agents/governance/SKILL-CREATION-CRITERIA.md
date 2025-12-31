# Skill Creation Criteria

## Purpose

Define when a problem warrants a dedicated skill versus direct LLM handling. Prevents both under-skilling (repeated protocol violations) and over-skilling (maintenance burden without benefit).

**Core principle** (from vexjoy): "Ask 'Should the LLM do this?' not 'Can it?'"

---

## The Solved/Unsolved Framework

### Solved Problems → Skill

Problems with **known, repeatable solutions** that benefit from deterministic execution:

| Characteristic | Example |
|----------------|---------|
| Has documented procedure | Git operations, PR creation |
| Failure mode is "skipped step" | Session protocol compliance |
| Outcome is verifiable | File existence, API response |
| Repeats frequently (>3x/week) | PR comment parsing |
| Error-prone when improvised | Markdown linting |

### Unsolved Problems → LLM Direct

Problems requiring **contextual judgment** where the "right answer" varies:

| Characteristic | Example |
|----------------|---------|
| Requires interpretation | "Is this code secure?" |
| Answer depends on context | Architecture decisions |
| Novel each time | Bug diagnosis |
| Benefits from debate | ADR review (multi-agent) |
| No single correct procedure | Code review feedback |

---

## Decision Matrix

Use this matrix to determine skill candidacy:

| Question | Yes → Skill | No → LLM |
|----------|-------------|----------|
| Is there a documented procedure? | Create skill | Handle directly |
| Do failures come from skipping steps? | Add phase gates | Trust LLM judgment |
| Is the output format fixed? | Skill standardizes | LLM adapts |
| Does it repeat >3x per week? | Skill amortizes cost | One-off handling |
| Can success be programmatically verified? | Skill enforces | LLM validates |

**Threshold**: If ≥3 answers are "Yes → Skill", create a skill.

---

## Skill Creation Checklist

Before creating a skill, verify:

### Required Justification

- [ ] **Frequency**: Problem occurs >3x per week
- [ ] **Failure pattern**: >2 incidents from same root cause
- [ ] **Procedure exists**: Can document step-by-step
- [ ] **Verification possible**: Can check success programmatically

### Anti-Patterns to Avoid

- [ ] NOT creating skill for one-time task
- [ ] NOT duplicating existing skill capability
- [ ] NOT wrapping simple tool invocation (use tool directly)
- [ ] NOT adding skill for subjective judgment tasks

### Design Requirements

- [ ] Clear entry criteria (when to invoke)
- [ ] Defined output format
- [ ] Phase gates for multi-step workflows (see [SKILL-PHASE-GATES.md](./SKILL-PHASE-GATES.md))
- [ ] Success metrics

---

## Creating New Skills: Use SkillCreator

**RECOMMENDED**: Use the `skillcreator` skill for all new skill creation.

```text
SkillCreator: create a skill for [your goal]
```

### Why SkillCreator

| Manual Creation | SkillCreator |
|-----------------|--------------|
| Ad-hoc analysis | 11 thinking models systematically applied |
| Varies by author | Consistent quality via evolution scoring (≥7) |
| No peer review | Multi-agent synthesis panel (unanimous approval) |
| Missing edge cases | Regression questioning until exhausted |
| Scripts optional | Automation analysis for agentic operation |

### SkillCreator Quality Gates

The skillcreator enforces these automatically:

| Gate | Requirement |
|------|-------------|
| Timelessness score | ≥7/10 (future-proof design) |
| Panel approval | 3/3 or 4/4 unanimous (Design, Usability, Evolution, Script agents) |
| Frontmatter validation | Only allowed properties |
| Extension points | ≥2 documented |
| Script self-verification | Scripts can verify their own output |

### When to Use SkillCreator

| Scenario | Approach |
|----------|----------|
| New production skill | **SkillCreator** (full analysis) |
| Quick prototype | Manual creation, then SkillCreator refinement |
| Skill modification | Direct edit (existing skills already validated) |
| Simple wrapper (<10 lines) | Manual creation acceptable |

### SkillCreator Process Overview

```text
Your Goal → Phase 1: Deep Analysis (11 lenses, regression questions)
          → Phase 2: Specification (XML with WHY for all decisions)
          → Phase 3: Generation (SKILL.md, references/, scripts/)
          → Phase 4: Synthesis Panel (unanimous approval required)
          → Production-Ready Skill
```

### Integration with This Document

SkillCreator uses these criteria internally:

- Solved/Unsolved Framework → Phase 1 requirement analysis
- Decision Matrix → Skill candidacy validation
- Complexity Tiers → Architecture pattern selection
- Phase Gates → Built into generated skills (Tier 2+)

**Reference**: [`.claude/skills/skillcreator/SKILL.md`](../../.claude/skills/skillcreator/SKILL.md)

---

## Examples

### Good Skill Candidates

| Problem | Why Skill? |
|---------|-----------|
| PR comment response | Fixed workflow: gather→triage→respond→verify |
| Session log creation | Repeats daily, fixed format, verifiable |
| Merge conflict resolution | Documented procedure, error-prone manual |
| Markdown fence fixing | Deterministic transformation |

### Bad Skill Candidates

| Problem | Why Not? |
|---------|----------|
| "Review this code" | Subjective, context-dependent |
| "Explain this error" | Novel each time, requires interpretation |
| "Design this feature" | No single correct procedure |
| "Is this approach good?" | Judgment call, benefits from debate |

### Borderline Cases

| Problem | Resolution |
|---------|------------|
| ADR review | **Hybrid**: Skill orchestrates debate, LLMs provide judgment |
| Security scan | **Skill with LLM gate**: Deterministic scan + LLM triage |
| Plan creation | **Multi-phase skill**: Structured workflow, LLM content |

---

## Skill Complexity Tiers

Match skill complexity to problem complexity:

### Tier 1: Simple Wrapper

- Single-step execution
- No phase gates needed
- Example: `fix-markdown-fences`

```markdown
---
name: fix-markdown-fences
description: Fix malformed markdown fence closings
---

# Fix Markdown Fences

Run: `npx markdownlint-cli2 --fix "**/*.md"`
```

### Tier 2: Multi-Step Workflow

- 2-4 phases
- Phase gates between major steps
- Example: `merge-resolver`

```markdown
---
name: merge-resolver
---

# Merge Resolver

## Phase 1: Gather Context
[Evidence gate]

## Phase 2: Analyze Conflicts
[Verification gate]

## Phase 3: Apply Resolution
```

### Tier 3: Orchestrated Pipeline

- Multiple agents/tools coordinated
- Review gates
- Example: `planner`

```markdown
---
name: planner
---

# Planner

## Planning Phase (N steps)
[Documentation gate]

## Review Phase (2 steps)
[Review gate: TW, QR]

## Execution Phase (7 steps)
[Multiple verification gates]
```

---

## Skill vs Agent Decision

Sometimes the question is "skill or agent?"

| Factor | Skill | Agent |
|--------|-------|-------|
| **Scope** | Single workflow | Domain expertise |
| **Invocation** | Direct (Skill tool) | Via Task tool |
| **Context** | Loads on demand | Full agent context |
| **Persistence** | Stateless | Can maintain state |
| **Token cost** | Low (skill-specific) | High (agent prompt) |

**Rule of thumb**:

- **Skill**: "Do this specific thing following this procedure"
- **Agent**: "Apply your expertise to this problem"

---

## Maintenance Burden Assessment

Before creating a skill, estimate maintenance:

| Factor | Low Burden | High Burden |
|--------|------------|-------------|
| Dependencies | None/stable | External APIs, tools |
| Update frequency | Rare | Weekly+ |
| Gate complexity | Simple checks | Complex validation |
| Documentation | Self-explanatory | Requires examples |

**Threshold**: If total burden is "High" in ≥2 factors, reconsider skill necessity.

---

## Metrics

Track skill health:

| Metric | Target | Action if Missed |
|--------|--------|------------------|
| Invocation frequency | >3x/week | Consider deprecation |
| Success rate | >90% | Review gates, update procedure |
| Bypass rate | <5% | Strengthen enforcement |
| Maintenance incidents | <1/month | Simplify or deprecate |

---

## Skill Retirement Criteria

Remove skills when:

- [ ] Invocation <1x/month for 3 months
- [ ] Success rate <70%
- [ ] Maintenance exceeds value
- [ ] Superseded by better approach (e.g., MCP tool)

---

## Related Documents

- [SKILL-PHASE-GATES.md](./SKILL-PHASE-GATES.md): Gate implementation
- [ADR-030](../architecture/ADR-030-skills-pattern-superiority.md): Skills vs subagents
- [ADR-033](../architecture/ADR-033-routing-level-enforcement-gates.md): Routing-level enforcement gates
- [Agent Design Principles](./agent-design-principles.md): Agent creation criteria
- [SkillCreator](../../.claude/skills/skillcreator/SKILL.md): Meta-skill for production-ready skill creation

---

*Governance Version: 1.3*
*Established: 2025-12-30*
*Updated: 2025-12-30 - Added SkillCreator guidance section*
*Debate Reference: critic recommendation (agent aabd3d0)*
