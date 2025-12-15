# Multi-Agent Impact Analysis Framework

## Overview

The Multi-Agent Impact Analysis Framework is a structured approach to comprehensive planning that ensures all affected domains (code, architecture, security, operations, quality) are considered before implementation begins.

## What Problem Does It Solve?

Without structured impact analysis, planning often misses critical cross-domain concerns:

- **Security vulnerabilities** discovered late in development
- **CI/CD breaks** when deployment impacts weren't considered
- **Quality regressions** when testing strategy wasn't planned
- **Architecture drift** when design implications weren't reviewed
- **Rework and delays** when issues surface during implementation

## How It Works

### 1. Trigger Conditions

The planner agent triggers impact analysis when planning changes that:

- Affect **3+ domains** (code, architecture, CI/CD, security, quality)
- Modify **core architectural patterns** or introduce new dependencies
- Touch **security-sensitive areas** (authentication, authorization, data)
- Impact **infrastructure** (build, deployment, CI/CD pipelines)
- Introduce **breaking changes** to public APIs or contracts

### 2. Consultation Process

```text
┌─────────────────────────────────────────────────┐
│ Planner identifies multi-domain change         │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ Planner orchestrates specialist consultations  │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │ Implementer  │  │  Architect   │           │
│  │ (Code)       │  │ (Design)     │           │
│  └──────────────┘  └──────────────┘           │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │  Security    │  │   DevOps     │           │
│  │ (Threats)    │  │ (Infra)      │           │
│  └──────────────┘  └──────────────┘           │
│                                                 │
│  ┌──────────────┐                              │
│  │      QA      │                              │
│  │  (Testing)   │                              │
│  └──────────────┘                              │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ Each specialist creates impact analysis doc    │
│ → .agents/planning/impact-analysis-[domain].md  │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ Planner aggregates findings into plan          │
│ - Cross-domain risks identified                │
│ - Integrated recommendations                   │
│ - Overall complexity assessment                │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ Critic reviews comprehensive plan              │
└─────────────────────────────────────────────────┘
```

### 3. Specialist Contributions

| Specialist | Analyzes | Key Outputs |
|------------|----------|-------------|
| **Implementer** | Code structure, patterns, testing complexity | Files to modify, code quality risks, effort estimate |
| **Architect** | Design consistency, architectural fit | ADR alignment, required patterns, long-term implications |
| **Security** | Attack surface, threat vectors, controls | Security risks, required mitigations, testing needs |
| **DevOps** | Build/deploy impact, infrastructure needs | Pipeline changes, secrets management, deployment strategy |
| **QA** | Test strategy, coverage, quality risks | Test types required, hard-to-test scenarios, effort |

### 4. Aggregated Output

The planner synthesizes all specialist findings into:

- **Cross-domain risk matrix** - Risks affecting multiple areas with mitigation strategies
- **Integrated recommendations** - Coordinated approach across all domains
- **Overall complexity assessment** - Realistic estimate considering all factors
- **Implementation sequence** - Logical order addressing dependencies

## Benefits

### Before Implementation Begins

✅ **All risks identified** - No surprises during development
✅ **Coordinated approach** - Infrastructure ready when code needs it
✅ **Realistic estimates** - Complexity understood across all domains
✅ **Quality built-in** - Testing strategy defined upfront

### During Implementation

✅ **Clear guidance** - Each domain's needs documented
✅ **Risk mitigation** - Strategies in place before problems occur
✅ **Smooth handoffs** - Specialists know what's expected

### After Implementation

✅ **Audit trail** - Decision rationale documented
✅ **Knowledge base** - Patterns for future similar changes
✅ **Reduced rework** - Issues caught in planning, not implementation

## When NOT to Use

The framework is **not needed** for:

- ❌ **Simple bug fixes** - Single file, clear scope
- ❌ **Documentation updates** - No code/infrastructure impact
- ❌ **Configuration tweaks** - Isolated changes with no cross-domain impact
- ❌ **Quick prototypes** - Exploratory work where full planning is premature

Use the standard simplified workflows for these cases.

## Example Scenario

**User Request**: "Add OAuth 2.0 authentication"

**Without Impact Analysis**:

- Planner creates basic plan
- Implementation discovers secret management needed → DevOps scramble
- Security testing needs identified late → Timeline slips
- OAuth mock server missing → Integration tests blocked
- Overall: 2 weeks estimated, 5 weeks actual

**With Impact Analysis**:

- Planner triggers multi-domain analysis
- Security identifies P0 token security controls upfront
- DevOps prepares Key Vault before implementation starts
- QA sets up OAuth mock server in CI pipeline early
- Implementer knows exact refactoring needed before starting
- Overall: 4 weeks estimated, 4 weeks actual (realistic from start)

See [IMPACT-ANALYSIS-EXAMPLE.md](IMPACT-ANALYSIS-EXAMPLE.md) for complete walkthrough.

## Getting Started

### For Planners

When creating a plan for a multi-domain change:

1. Identify affected domains using the trigger conditions
2. Invoke each required specialist agent with structured prompt:
   ```text
   Task(subagent_type="[specialist]", prompt="Impact Analysis Request: [Feature]...")
   ```
3. Collect impact analysis documents from `.agents/planning/`
4. Synthesize findings into comprehensive plan
5. Route to critic for validation

### For Specialists

When planner requests impact analysis:

1. Analyze the change from your domain's perspective
2. Use the impact analysis template for your role
3. Save findings to `.agents/planning/impact-analysis-[feature]-[domain].md`
4. Return to planner with complexity assessment

### For Users

Trust the process:

- Initial estimates may seem high (they're realistic)
- Upfront planning prevents downstream rework
- All specialists aligned from the start
- Risks identified before they become problems

## Templates

Each specialist agent's instructions include complete impact analysis templates. See:

- `claude/implementer.md` - Code impact analysis template
- `claude/architect.md` - Architecture impact analysis template
- `claude/security.md` - Security impact analysis template
- `claude/devops.md` - DevOps impact analysis template
- `claude/qa.md` - QA impact analysis template

Same templates available in `copilot-cli/*.agent.md` and `vs-code-agents/*.agent.md`.

## References

- **PRD**: [GitHub Issue - PRD: Multi-Agent Impact Analysis Framework](https://github.com/rjmurillo/ai-agents/issues/[number])
- **Example**: [IMPACT-ANALYSIS-EXAMPLE.md](IMPACT-ANALYSIS-EXAMPLE.md)
- **Agent Instructions**: See individual agent files for detailed templates
