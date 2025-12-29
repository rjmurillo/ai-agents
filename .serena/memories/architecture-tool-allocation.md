# Skill-Architecture-001: Role-Specific Tool Allocation

**Statement**: Agents get tools matching their responsibilities only

**Context**: Agent tool configuration and ADR-003

**Evidence**: ADR-003 reduced tools from ~58 blanket to 3-9 role-specific

**Atomicity**: 92%

**Impact**: 9/10

## Pattern

- Security agent = security tools (code scanning, secret detection)
- Implementer = code tools (execute, edit, github/push)
- Analyst = research tools (web, search, read-only github)

## Anti-Pattern

- Blanket `github/*` (~77 tools) to all agents
- Generic tool allocation regardless of role

**Source**: `.agents/architecture/ADR-003-agent-tool-selection-criteria.md`
