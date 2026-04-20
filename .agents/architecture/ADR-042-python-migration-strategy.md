# ADR-042: Python Migration Strategy

## Status

Accepted

## Date

2026-01-17

## Context

The ai-agents project has operated under ADR-005 (PowerShell-only scripting) since December 2025. This decision was appropriate when:

1. The project was Windows-first
2. PowerShell had mature CI/CD tooling
3. No external Python dependencies existed

The landscape has shifted:

1. **skill-installer Adoption**: PR #962 replaced PowerShell installation scripts with [skill-installer](https://github.com/rjmurillo/skill-installer), introducing Python 3.10+ and UV as project prerequisites

2. **AI/ML Ecosystem**: Python dominates the AI/ML landscape:
   - Anthropic SDK (official Python support, no PowerShell SDK)
   - LangChain, LlamaIndex, and other agent frameworks are Python-native
   - Machine learning libraries (transformers, torch, numpy) are Python-only
   - MCP servers and clients are predominantly Python

3. **Developer Ecosystem**: Python has significant developer adoption and momentum:
   - Stack Overflow 2025: Python had largest year-over-year growth (+7 points)
   - More contributors familiar with Python than PowerShell
   - Better IDE support, linting, and debugging tools

4. **Existing Exceptions**: ADR-005 already has two Python exceptions:
   - SkillForge developer tools (`.claude/skills/SkillForge/scripts/`)
   - Claude Code hooks with LLM integration (`.claude/hooks/`)

5. **Token Efficiency Inversion**: The original ADR-005 rationale was token efficiency (agents wasted tokens generating Python then reimplementing in PowerShell). With Python as a prerequisite and AI/ML integration as a priority, this rationale has inverted.

## Decision

**Migrate the ai-agents project from PowerShell to Python as the primary scripting language over a 12-24 month phased migration period.**

This decision:

1. **Supersedes ADR-005** for new development
2. **Establishes Python 3.10+** as the project language standard
3. **Deprecates PowerShell** for new scripts (existing scripts may be migrated over time)
4. **Adopts UV** as the Python package manager

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Keep PowerShell-only** | No migration effort, existing tooling works | Blocks AI/ML integration, skill-installer already requires Python | Python prerequisite already exists; blocking AI integration is counterproductive |
| **Hybrid approach** | Gradual transition, low risk | Fragments testing (Pester + pytest), maintains two languages indefinitely | Creates permanent maintenance burden; does not solve the ecosystem mismatch |
| **Python-first with phased migration (chosen)** | AI/ML native, larger ecosystem, incremental transition | Migration effort, learning curve for PowerShell-familiar maintainers | Best long-term alignment with project direction; acknowledges 235 PowerShell files require multi-year transition |

### Trade-offs

| Trade-off | Impact | Mitigation |
|-----------|--------|------------|
| Migration effort | Medium | Phased approach; existing PowerShell scripts continue working |
| Pester test investment | Low | Pester tests remain valid until scripts migrated |
| PowerShell expertise | Low | Python has gentler learning curve; contributors likely already know Python |
| Windows native tooling | Low | Python works excellently on Windows via UV |

## Consequences

### Positive

1. **AI/ML Integration**: Direct access to Anthropic SDK, LangChain, and ML libraries
2. **skill-installer Native**: Installation tool is Python; align project tooling
3. **Larger Contributor Pool**: More developers know Python than PowerShell
4. **Better Tooling**: mypy for types, pytest for testing, ruff for linting
5. **MCP Compatibility**: MCP servers and clients are predominantly Python
6. **Future-Proof**: AI tooling is converging on Python

### Negative

1. **Migration Effort**: Existing PowerShell scripts need eventual rewrite
   - **Mitigation**: Phased approach; migrate on-touch or by priority
2. **Pester Tests**: Will need conversion to pytest
   - **Mitigation**: Can run both test frameworks during transition
3. **Learning Curve**: Contributors familiar only with PowerShell
   - **Mitigation**: Python is widely taught; extensive documentation

### Neutral

1. **GitHub Actions Workflows**: Continue using minimal shell commands (ADR-006 still applies)
2. **Cross-Platform**: Both PowerShell Core and Python work on all platforms
3. **UV Requirement**: Already a prerequisite via skill-installer

## Implementation Notes

### Phase 1: Foundation (Current)

- [x] Python 3.10+ as prerequisite (via skill-installer)
- [x] UV as package manager (via skill-installer)
- [x] marketplace.json for agent discovery
- [ ] pyproject.toml for project configuration
- [ ] pytest infrastructure setup

### Phase 2: New Development

- All new scripts SHOULD be Python
- PowerShell may still be used for:
  - Quick fixes to existing PowerShell scripts
  - PowerShell-specific operations (Windows registry, etc.)

### Phase 3: Migration (Future)

Priority order for migration:

1. **High-traffic scripts**: Frequently modified scripts
2. **CI infrastructure**: Workflow scripts
3. **Skills**: `.claude/skills/github/` and similar
4. **Build system**: `build/` directory

### Migration Guidance

When migrating a PowerShell script:

1. Create Python equivalent in same location (`.ps1` → `.py`)
2. Migrate Pester tests to pytest
3. Update callers to use Python version
4. Mark PowerShell version as deprecated
5. Remove PowerShell version after verification period

## Related Decisions

- **Supersedes**: [ADR-005: PowerShell-Only Scripting Standard](./ADR-005-powershell-only-scripting.md)
- **Companion**: [ADR-006: Thin Workflows, Testable Modules](./ADR-006-thin-workflows-testable-modules.md) (still applies)
- **Related**: PR #962 (skill-installer adoption)

## References

- [skill-installer](https://github.com/rjmurillo/skill-installer): Python TUI for agent installation
- [UV](https://docs.astral.sh/uv/): Fast Python package manager
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python): Official Python SDK
- [Stack Overflow Developer Survey 2025](https://survey.stackoverflow.co/2025/): Python largest YoY growth (+7 points)

---

## Amendment 1: Scope Python-First to Internal Automation

### Date

2026-04-13

### Status

Proposed

### Context

Stage 1 of the Claude Kit Vendor initiative (#1574, #1619) delivers `npx @rjmurillo/ai-agents init`, an npm CLI that vendors the `.claude/` kit into target repositories. The target audience lives in the npm/Node.js ecosystem. Requiring Python (`pipx`) for a tool consumed via `npx` creates unnecessary friction.

ADR-042 was written when all project tooling was internal automation: CI scripts, GitHub skill scripts, hooks, session tooling. The decision to standardize on Python remains correct for that surface. However, the project now has a second surface: user-facing distribution packages published to npm, consumed by developers who may not have Python installed.

Premise P4 from the Stage 1 plan: "ADR-042 (Python first) can be amended to scope 'Python first' to internal automation. User-facing distribution surfaces may use TypeScript when the target audience demands it."

### Decision

Scope the Python-first mandate to **internal automation**. Permit TypeScript (or other languages native to the target ecosystem) for **user-facing distribution surfaces**.

**Internal automation** (Python-first applies):

- CI/CD scripts and workflow helpers
- GitHub skill scripts (`.claude/skills/github/scripts/`)
- Claude Code hooks (`.claude/hooks/`)
- Session protocol tooling
- Build and test infrastructure
- Any script executed within this repository's development workflow

**User-facing distribution surfaces** (TypeScript permitted):

- npm packages published under `@rjmurillo/ai-agents`
- CLI entry points consumed via `npx`
- Any artifact whose primary consumers install it from a non-Python package registry

### Rationale

| Factor | Internal automation | User-facing distribution |
|--------|-------------------|--------------------------|
| Consumer | Repository maintainers | External developers |
| Runtime guarantee | Python 3.10+ via UV | Node.js via npx |
| Ecosystem alignment | AI/ML libraries, Anthropic SDK | npm, Claude Code, Copilot |
| Correct language | Python | TypeScript |

Forcing Python on npm consumers violates the Pit of Success principle: developers should fall into the correct pattern without extra setup. A `pipx` prerequisite for an `npx` workflow is the opposite of that.

### Consequences

1. The `ai-agents-cli` package (Stage 1) is written in TypeScript, bundled with bun, published to npm.
2. All internal automation continues under Python-first per the original ADR-042 decision.
3. If a future distribution surface targets PyPI, Python is the correct choice for that surface.
4. The language choice follows the consumer's ecosystem, not the producer's preference.

### What Does Not Change

- ADR-042's core decision for internal automation remains intact.
- The phased PowerShell-to-Python migration continues as planned.
- ADR-006 (thin workflows, testable modules) still applies.
- UV remains the Python package manager for internal tooling.

---

## Amendment Log

| Date | Change | Approved By |
|------|--------|-------------|
| 2026-01-17 | Initial adoption | Repository owner (PR #963) |
| 2026-04-13 | Amendment 1: Scope Python-first to internal automation, permit TypeScript for user-facing distribution | Pending adr-review |

---

*Template Version: 1.0*
*Supersedes: ADR-005*
