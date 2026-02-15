# Architecture: Rolespecific Tool Allocation 92

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

## Related

- [architecture-002-model-selection-by-complexity-85](architecture-002-model-selection-by-complexity-85.md)
- [architecture-003-composite-action-pattern-for-github-actions-100](architecture-003-composite-action-pattern-for-github-actions-100.md)
- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-004-producerconsumer-prompt-coordination-90](architecture-004-producerconsumer-prompt-coordination-90.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
