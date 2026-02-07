# ADR-045: Framework Extraction via Plugin Marketplace

## Status

Proposed

## Date

2026-02-07

## Context

The `rjmurillo/ai-agents` repository contains a multi-agent framework that has grown organically alongside project-specific content. An inventory analysis reveals:

- ~65% of the codebase is reusable framework infrastructure (agents, shared skills, session protocol, quality gates)
- ~25% is project-specific content (domain skills, custom workflows, project configuration)
- ~10% is hybrid (framework code with hard-coded project paths)

This co-location creates several problems:

1. **Cannot share the framework**: Other projects cannot consume the agent definitions, skills, or session protocol without cloning the entire repo
2. **Cannot publish as plugin**: Claude Code's plugin marketplace system requires a standalone repository with `.claude-plugin/` manifests
3. **Coupling obscures boundaries**: Framework code references project-specific paths, making it unclear what is reusable
4. **Maintenance burden**: Changes to framework components must navigate project-specific files, increasing cognitive load

Claude Code now provides a stable plugin marketplace system (researched in session 1180, documented in `.agents/analysis/claude-code-plugin-marketplaces.md`) that supports:

- Declarative JSON catalogs (`.claude-plugin/marketplace.json`)
- Multiple hosting options (GitHub repos, Git URLs, local paths)
- Plugin namespacing (`/plugin-name:skill`) to prevent conflicts
- Team-wide configuration via `settings.json`

### Prerequisites

- **v0.3.0** (memory enhancement): Must ship first to stabilize memory APIs
- **v0.3.1** (PowerShell-to-Python migration, ADR-042): Must complete before extraction so all extracted code is Python. Extracting PowerShell code only to immediately migrate it in awesome-ai would double the effort.

## Decision

**Extract the reusable multi-agent framework from `rjmurillo/ai-agents` into a new repository `rjmurillo/awesome-ai`, published as a Claude Code plugin marketplace with 4 plugins.**

The 4 plugins are:

| Plugin | Contents | Rationale |
|--------|----------|-----------|
| `core-agents` | 26 agent definitions, 18 shared templates, build/generation system, governance templates | Zero-coupling, cleanest extraction |
| `framework-skills` | ~28 reusable skills with pytest coverage | Skills usable across any project |
| `session-protocol` | 12+ hooks, 3 session skills, SESSION-PROTOCOL template | Session lifecycle is a cohesive unit |
| `quality-gates` | 6 enforcement hooks, 4 composite actions, 27 PR quality prompts, CI templates | Quality enforcement is a cohesive unit |

After extraction, `ai-agents` becomes a **reference implementation** that consumes `awesome-ai` as a plugin marketplace, containing only project-specific configuration, domain skills, and customizations.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Keep monorepo** | No migration effort, no namespace changes | Cannot share framework, cannot publish as plugin, coupling grows | Blocks the primary goal of framework reuse |
| **Single plugin** | Simpler structure, one install | All-or-nothing adoption, large plugin size | Users should install only what they need |
| **Monorepo with workspace** | Single repo, local references | Claude Code plugins require standalone repos for GitHub source | Plugin marketplace does not support monorepo workspaces |
| **4 plugins in marketplace (chosen)** | Granular adoption, clear boundaries, aligns with plugin format | Namespace migration, 4 manifests to maintain | Best balance of granularity and maintenance |
| **npm/pip package** | Standard package distribution | Not a Claude Code plugin, no skill/hook/agent support | Does not integrate with Claude Code's plugin system |

### Path Abstraction

Plugins are installed to a cache directory, not the project root. Framework code that references consumer paths (e.g., `.agents/sessions/`) must use environment variables with sensible defaults:

```python
SESSION_DIR = os.environ.get("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
```

Internal plugin paths use `${CLAUDE_PLUGIN_ROOT}` which Claude Code resolves at runtime.

### Namespace Impact

Skills change from `/skill-name` to `/awesome-ai:skill-name`. This is a breaking change for:

- SKILL.md files referencing other skills
- CLAUDE.md and AGENTS.md documentation
- Agent prompts that invoke skills
- CI workflows that call skills

Mitigation: Automated grep sweep in Phase 4 before removing originals.

### Versioning Strategy

awesome-ai starts at v0.4.0, aligned with the ai-agents milestone. This provides a single version truth during extraction and makes it clear which ai-agents milestone corresponds to which awesome-ai release.

## Consequences

### Positive

- Framework becomes independently installable via `claude plugin marketplace add rjmurillo/awesome-ai`
- Other projects can adopt agents, skills, or protocol without project-specific baggage
- Clear separation of concerns between framework and domain code
- 4-plugin granularity lets users install only what they need
- Versioned releases enable stable consumption

### Negative

- Namespace migration requires updating all skill references in ai-agents
- Two repositories to maintain instead of one
- Contributors must understand the framework/domain boundary
- Plugin cache isolation may introduce path resolution issues (mitigated by env vars)

### Neutral

- ai-agents becomes smaller and more focused on project-specific content
- Development workflow changes: framework changes go to awesome-ai, project changes stay in ai-agents

## Implementation

See `.agents/projects/v0.4.0/PLAN.md` for the detailed 6-phase implementation plan.

## References

- [Plugin Marketplace Research](../analysis/claude-code-plugin-marketplaces.md) (session 1180)
- [v0.4.0 Plan](../projects/v0.4.0/PLAN.md)
- [ADR-042: Python Migration Strategy](ADR-042-python-migration-strategy.md) (prerequisite)
- [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins)
- [Claude Code Marketplace Docs](https://code.claude.com/docs/en/plugin-marketplaces)
