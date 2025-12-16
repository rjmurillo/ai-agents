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

## Related Documents

- Source: `.agents/architecture/ADR-0003-agent-tool-selection-criteria.md`
- Source: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`
- Related: skills-workflow (tool usage in workflows)
