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

## Amendment Log

| Date | Change | Approved By |
|------|--------|-------------|
| 2026-01-17 | Initial adoption | Repository owner (PR #963) |

---

*Template Version: 1.0*
*Supersedes: ADR-005*
