# Architecture Skills

**Extracted**: 2025-12-16
**Source**: `.agents/architecture/` directory (ADRs)

## Skill-Architecture-001: Role-Specific Tool Allocation (92%)

**Statement**: Agents get tools matching their responsibilities only

**Context**: Agent tool configuration and ADR-0003

**Evidence**: ADR-0003 reduced tools from ~58 blanket to 3-9 role-specific

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

- Security agent = security tools (code scanning, secret detection)
- Implementer = code tools (execute, edit, github/push)
- Analyst = research tools (web, search, read-only github)

**Anti-Pattern**:

- Blanket `github/*` (~77 tools) to all agents
- Generic tool allocation regardless of role

**Source**: `.agents/architecture/ADR-0003-agent-tool-selection-criteria.md`

---

## Skill-Architecture-002: Model Selection by Complexity (85%)

**Statement**: Match AI model tier to task complexity for cost efficiency

**Context**: Agent configuration and resource optimization

**Evidence**: ADR-002 model selection optimization

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 7/10

**Tiers**:

- **Opus**: Complex reasoning, architecture, security
- **Sonnet**: Balanced tasks, implementation, QA
- **Haiku**: Simple/fast, formatting, simple queries

**Benefit**: Cost reduction while maintaining quality

**Source**: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`

---

## Skill-Architecture-003: Composite Action Pattern for GitHub Actions (100%)

**Statement**: When ≥2 workflows share logic, extract to composite action with parameterized inputs for reusability

**Context**: GitHub Actions workflow design. Apply during architecture phase when duplication detected.

**Trigger**: Designing ≥2 workflows with similar logic

**Evidence**: Session 03 (2025-12-18): 1 composite action (342 LOC) shared by 4 workflows saved ~1,368 LOC. Single reusable `ai-review` action with parameterized inputs (agent, prompt-file, context) eliminated duplication.

**Atomicity**: 100%

- Specific trigger (≥2 workflows) ✓
- Single concept (composite action extraction) ✓
- Actionable (create composite action) ✓
- Measurable (LOC saved = action LOC × uses - action LOC) ✓

**Impact**: 9/10 - High reusability, reduced maintenance burden

**Category**: CI/CD Architecture

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Pattern**:

```yaml
# .github/actions/my-action/action.yml
name: My Reusable Action
inputs:
  param1:
    description: 'Parameterized input'
    required: true
runs:
  using: composite
  steps:
    - name: Step 1
      shell: bash
      run: echo "${{ inputs.param1 }}"
```

**Usage in Workflows**:

```yaml
- uses: ./.github/actions/my-action
  with:
    param1: value
```

---

## Skill-Architecture-004: Producer-Consumer Prompt Coordination (90%)

**Statement**: When updating agent workflows, modify both producer and consumer prompts

**Context**: Agent coordination architecture, workflow changes

**Trigger**: Updating agent handoff protocols or output formats

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature required coordinated updates:

- Producer: `retrospective.md` - Added structured handoff output format (tables with skill/memory/git sections)
- Consumer: `orchestrator.md` - Added post-retrospective workflow to parse and process those tables

Single-sided update would break automation. Both prompts updated in commit `d7489ba`.

**Atomicity**: 90%

- Specific actors (producer and consumer) ✓
- Single concept (coordinated updates) ✓
- Actionable (modify both) ✓
- Measurable (verify both files changed) ✓
- Length: 10 words ✓

**Impact**: 9/10 - Prevents broken handoffs, enables automation

**Category**: Agent Coordination

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (Session 17 retrospective auto-handoff)

**Pattern**:

| Agent Role | File | Update Type |
|------------|------|-------------|
| Producer | retrospective.md | Define output format |
| Consumer | orchestrator.md | Parse and process format |

**Coordination Checklist**:

- [ ] Producer defines structured output (tables, sections, tokens)
- [ ] Consumer documents parsing logic
- [ ] Both prompts reference same field names/structure
- [ ] Example output provided in producer prompt
- [ ] Error handling defined in consumer prompt

---

## Related Documents

- Source: `.agents/architecture/ADR-0003-agent-tool-selection-criteria.md`
- Source: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`
- Source: `.agents/retrospective/2025-12-18-ai-workflow-implementation.md`
- Source: `.agents/sessions/2025-12-18-session-17-retrospective-auto-handoff.md`
- Related: skills-workflow (tool usage in workflows)
- Related: skills-agent-workflow-phase3 (Skill-AgentWorkflow-005)
