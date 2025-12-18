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

## Related Documents

- Source: `.agents/architecture/ADR-0003-agent-tool-selection-criteria.md`
- Source: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`
- Source: `.agents/retrospective/2025-12-18-ai-workflow-implementation.md`
- Related: skills-workflow (tool usage in workflows)
