# Impact Analysis Framework

For complex, multi-domain changes, orchestrator manages impact analysis consultations with specialist agents.

Since subagents cannot delegate, milestone-planner creates the analysis plan and orchestrator executes each specialist consultation.

## When to Use

- **Multi-domain changes**: Affects 3+ areas (code, architecture, CI/CD, security, quality)
- **Architecture changes**: Modifies core patterns or introduces new dependencies
- **Security-sensitive changes**: Touches authentication, authorization, data handling
- **Infrastructure changes**: Affects build, deployment, or CI/CD pipelines
- **Breaking changes**: Modifies public APIs or contracts

## Consultation Process

```text
1. Orchestrator routes to milestone-planner with impact analysis flag
2. Milestone-planner identifies change scope, affected domains, creates analysis plan
3. Milestone-planner returns plan to orchestrator
4. Orchestrator invokes specialist agents (sequentially or in parallel):
   - implementer: Code impact
   - architect: Design impact
   - security: Security impact
   - devops: Operations impact
   - qa: Quality impact
5. Orchestrator aggregates findings
6. Orchestrator routes to critic for validation
```

## Handling Failed Consultations

1. **Retry once** with clarified prompt
2. If still failing, **log gap** and proceed with partial analysis
3. **Flag in plan** as "Incomplete: [missing domain]"
4. Critic must acknowledge incomplete consultation in review

## Impact Analysis Outputs

Each specialist creates: `.agents/planning/impact-analysis-[domain]-[feature].md`

## Domain Identification

Tasks are analyzed for which domains they affect:

| Domain | Scope |
|--------|-------|
| Code | Application source, business logic |
| Architecture | System design, patterns, structure |
| Security | Auth, data protection, vulnerabilities |
| Operations | CI/CD, deployment, infrastructure |
| Quality | Testing, coverage, verification |
| Data | Schema, migrations, storage |
| API | External interfaces, contracts |
| UX | User experience, frontend |

## Complexity from Domain Count

| Domain Count | Complexity | Strategy |
|--------------|------------|----------|
| 1 | Simple | Single specialist agent |
| 2 | Standard | Sequential 2-3 agents |
| 3+ | Complex | Full orchestration with impact analysis |

Security, Strategic, and Ideation tasks are always treated as Complex.
