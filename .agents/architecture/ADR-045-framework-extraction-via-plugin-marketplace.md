# ADR-045: Framework Extraction via Plugin Marketplace

## Status

Proposed (Round 2 review pending)

## Date

2026-02-07

## Decision Drivers

- **Separation of concerns**: Framework code and project-specific code are co-located, obscuring boundaries and increasing cognitive load during maintenance.
- **Dog-fooding**: Publishing as a plugin marketplace validates the format we recommend to consumers.
- **Future shareability**: Clean extraction enables sharing IF external demand materializes. No external demand exists today.
- **Python-first prerequisite**: ADR-042 migration must complete before extraction to avoid extracting PowerShell code that immediately needs rewriting.

## Stakeholders

| Role | Who | Responsibility |
|------|-----|----------------|
| Decision maker | Repository owner | Approve/reject |
| Implementer | Repository owner | Execute extraction |
| Consulted | 6-agent review panel | Architectural, security, feasibility review |
| Informed | Future consumers (if any) | Adoption guidance |

Note: This is a single-maintainer project. All roles collapse to the repository owner, with AI agents providing review coverage.

## Context

The `rjmurillo/ai-agents` repository contains a multi-agent framework that has grown alongside project-specific content. A formal inventory audit (168 files, 5 categories) found:

- ~55% reusable framework infrastructure (agents, shared skills, session protocol, quality gates)
- ~8% project-specific content (domain skills, custom workflows, project configuration)
- ~37% hybrid (framework code with hard-coded project paths requiring parameterization)

**Source**: [Inventory Audit](../analysis/adr-045-inventory-audit.md). The 37% hybrid percentage exceeds the 20% re-evaluation threshold, but the extraction is justified because path parameterization is a one-time cost with long-term maintainability gains. See Inventory Verification section below.

This co-location creates problems:

1. **Cannot publish as plugin**: Claude Code's plugin marketplace requires a standalone repository with `.claude-plugin/` manifests
2. **Coupling obscures boundaries**: Framework code references project-specific paths, making reusability unclear
3. **Maintenance burden**: Changes to framework components must navigate project-specific files

**What this is NOT**: There is no validated external demand for this framework. No other projects have requested it. Third-party alternatives exist (claude-flow, agents, multi-agent-shogun). This decision is motivated by separation of concerns and dog-fooding the plugin format, not by proven external adoption.

Claude Code provides a stable plugin marketplace system (researched in session 1180, documented in `.agents/analysis/claude-code-plugin-marketplaces.md`) that supports:

- Declarative JSON catalogs (`.claude-plugin/marketplace.json`)
- Multiple hosting options (GitHub repos, Git URLs, local paths)
- Plugin namespacing (`/plugin-name:skill`) to prevent conflicts
- Team-wide configuration via `settings.json`

### Prerequisites

- **v0.3.0** (memory enhancement): Must ship first to stabilize memory APIs.
- **v0.3.1** (PowerShell-to-Python migration, ADR-042): Must complete before extraction so all extracted code is Python. Extracting PowerShell code only to immediately migrate it in awesome-ai would double the effort. v0.3.1 estimated completion: Jan 2027.
- **Earliest execution start: Q1 2027 (post-v0.3.1 completion).** No v0.4.0 implementation work begins until v0.3.1 ships. Planning artifacts are forward-looking documentation only.

## Decision

**Extract the reusable multi-agent framework from `rjmurillo/ai-agents` into a new repository `rjmurillo/awesome-ai`, published as a Claude Code plugin marketplace with 4 plugins.**

The 4 plugins are:

| Plugin | Contents | Coupling Assessment |
|--------|----------|---------------------|
| `core-agents` | 26 agent definitions, 18 shared templates, build/generation system, governance templates | Low coupling. 14 of 18 templates contain output path directives (e.g., `Save to: .agents/analysis/...`) that require parameterization before extraction. Path parameterization is Phase 1 scope. |
| `framework-skills` | ~28 reusable skills with pytest coverage | Medium coupling. Skills reference consumer paths and may depend on PowerShell wrappers pending migration. |
| `session-protocol` | 12+ hooks, 3 session skills, SESSION-PROTOCOL template | Medium coupling. Hooks reference consumer session directories. |
| `quality-gates` | 6 enforcement hooks, 4 composite actions, 27 PR quality prompts, CI templates | Low coupling. Primarily self-contained enforcement logic. |

After extraction, `ai-agents` becomes a **reference implementation** that consumes `awesome-ai` as a plugin marketplace, containing only project-specific configuration, domain skills, and customizations.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Keep monorepo** | No migration effort, no namespace changes | Cannot publish as plugin, coupling grows, no separation of concerns | Blocks the primary goal of clean framework boundaries |
| **Single plugin** | Simpler structure, one install | All-or-nothing adoption, large plugin size | Users should install only what they need |
| **Monorepo with workspace** | Single repo, local references | Claude Code plugins require standalone repos for GitHub source | Plugin marketplace does not support monorepo workspaces |
| **4 plugins in marketplace (chosen)** | Granular adoption, clear boundaries, aligns with plugin format | Namespace migration, 4 manifests to maintain | Best balance of granularity and maintenance |
| **npm/pip package** | Standard package distribution | Not a Claude Code plugin, no skill/hook/agent support | Does not integrate with Claude Code's plugin system |

### Path Abstraction

Plugins are installed to a cache directory, not the project root. Framework code that references consumer paths (e.g., `.agents/sessions/`) must use environment variables with sensible defaults:

```python
import os

SESSION_DIR = os.environ.get("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
```

Internal plugin paths use `${CLAUDE_PLUGIN_ROOT}` which Claude Code resolves at runtime.

**Path validation requirements:**

- Scripts MUST validate that target paths exist before writing. Raise an exception on missing directories. Never fail silently.
- Path traversal defense: Use `os.path.realpath()` with a containment check against the project root. Reject any resolved path that escapes the project directory.
- Failure behavior: Raise a descriptive exception. Log the attempted path and the containment boundary. Never write to an unvalidated path.

```python
import os

def safe_resolve(path: str, project_root: str) -> str:
    """Resolve path and verify it stays within project root."""
    resolved = os.path.realpath(path)
    root = os.path.realpath(project_root)
    if not resolved.startswith(root + os.sep) and resolved != root:
        raise ValueError(
            f"Path '{path}' resolves to '{resolved}', "
            f"which is outside project root '{root}'"
        )
    return resolved
```

### Namespace Impact

Skills change from `/skill-name` to `/awesome-ai:skill-name`. This is a breaking change for:

- SKILL.md files referencing other skills
- CLAUDE.md and AGENTS.md documentation
- Agent prompts that invoke skills
- CI workflows that call skills

Mitigation: Automated grep sweep in Phase 4 before removing originals. The sweep must cover YAML frontmatter, string interpolation in Python/PowerShell, and external documentation references.

### Versioning Strategy

awesome-ai starts at v0.4.0, aligned with the ai-agents milestone. This provides a single version truth during extraction and makes it clear which ai-agents milestone corresponds to which awesome-ai release.

## Inventory Verification

A formal inventory audit of 168 files across 5 categories was completed. See [Inventory Audit](../analysis/adr-045-inventory-audit.md) for file-by-file classification.

**Results**: 55% framework (92 files), 8% domain (13 files), 37% hybrid (63 files).

**Key findings:**

- Agent templates: 100% hybrid (all 18 contain hard-coded `.agents/` output paths)
- Hooks: 77% hybrid (14 of 18 reference `.agents/` directories for enforcement)
- Skills: 34% hybrid (14 of 41 have hard-coded paths)
- The 37% hybrid exceeds the 20% re-evaluation threshold

**Re-evaluation decision**: Proceed with extraction. Path parameterization is a one-time cost (63 files) that produces long-term separation of concerns. The extraction boundary remains the same; the effort estimate is revised upward.

**Methodology used:**

1. Grep for project-specific references: `.agents/`, `ai-agents`, `rjmurillo`, `templates/`
2. Classify each file as framework (zero project references), domain (project-specific), or hybrid (framework logic with project paths)
3. Record classification rationale and grep counts per file

**Verification script requirement:** A Python script must produce the inventory report in CI. The script takes the repository root as input and outputs a CSV with columns: file path, classification, and matched patterns. Acceptance criteria: classification percentages match the audit baseline within 5 percentage points.

## Security Model

### Plugin Integrity

- Consumers MUST pin `awesome-ai` to a specific SHA or Git tag. Mutable branch references (e.g., `main`) are not acceptable for production consumption.
- Plugin updates require explicit consumer action: pull the new version, review changes, update the pin. No auto-update mechanism.
- CI templates distributed by plugins MUST use SHA-pinned GitHub Actions (per existing PROJECT-CONSTRAINTS.md).
- Future consideration: Adopt GitHub artifact attestation for supply chain verification when the feature stabilizes.

### Hook Execution

Plugin hooks run in the consumer's process context with the consumer's full privileges. This is a Claude Code platform characteristic, not something this project can sandbox.

- Hooks can access the filesystem, network, and environment variables of the consumer process. This is identical to any Claude Code hook from any source.
- Consumers SHOULD review hook code before enabling a plugin, the same way they review any third-party dependency.
- If Claude Code introduces a hook permission model in the future, awesome-ai will adopt it.

### Secret Exposure

- Hooks execute with access to consumer environment variables. No secret masking or filtering is implemented at the plugin level.
- Mitigation: This is the same trust model as any Claude Code hook. Consumers who do not trust the plugin source should not install it.
- Future consideration: If Claude Code adds secret masking for hooks, adopt it.

## Reversibility

**Reversibility level: Medium.**

If extraction fails or the plugin marketplace format proves unstable, `ai-agents` can revert by:

1. Removing the marketplace reference from configuration
2. Restoring extracted files from git history (all originals remain in git)
3. Reverting namespace changes (`/awesome-ai:skill` back to `/skill`)

The expand-contract approach (add plugin, verify functionality, then remove originals) minimizes risk. At no point during migration are files deleted before the plugin equivalent is verified.

**Vendor lock-in: Low.** Claude Code's plugin marketplace is the distribution mechanism, but the underlying content is plain files (Markdown, Python, JSON). If the marketplace format is abandoned, the repository remains a standard Git repo consumable via submodules, subtree, or copy.

**Exit strategy:** If Claude Code plugin marketplace is deprecated, fall back to Git submodules or direct file copy. Estimated effort to switch: 2-4 sessions.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Plugin marketplace format instability | Medium | High | Pin to documented schema version. Monitor Claude Code changelogs. P1-2 from review identified issues #17089 and #17361 as evidence of undocumented breaking changes. |
| Single maintainer capacity conflict | High | Medium | v0.4.0 does not begin execution until v0.3.1 completes. No concurrent milestone work. |
| Path parameterization more complex than estimated | Medium | Medium | Formal inventory audit (see above) quantifies actual scope before committing to timeline. |
| External demand never materializes | High | Low | Extraction still provides separation of concerns and maintainability benefits for the primary consumer. Framework is not wasted even without external adoption. |

## Consequences

### Positive

- Framework becomes independently installable via `claude plugin marketplace add rjmurillo/awesome-ai`
- Clear separation of concerns between framework and domain code
- 4-plugin granularity lets consumers install only what they need
- Versioned releases enable stable consumption
- Dog-foods the plugin marketplace format

### Negative

- Namespace migration requires updating all skill references in ai-agents
- Two repositories mean 2x CI/CD pipelines, 2x dependency management, and cross-repo coordination for breaking changes
- Contributors must understand the framework/domain boundary
- Plugin cache isolation may introduce path resolution issues (mitigated by env vars and validation)

### Neutral

- ai-agents becomes smaller and more focused on project-specific content
- Development workflow changes: framework changes go to awesome-ai, project changes stay in ai-agents

## Confirmation

Implementation compliance will be verified through:

1. **Inventory audit script** runs in CI and produces classification report
2. **Path validation tests** verify `safe_resolve()` rejects traversal attempts
3. **Namespace migration test** greps both repos for unqualified skill references post-extraction
4. **Expand-contract verification** confirms plugin functionality before original removal
5. **Pin verification** confirms all consumer references use SHA/tag, not branch

## Implementation

See `.agents/projects/v0.4.0/PLAN.md` for the detailed phased implementation plan and session estimates.

## Related Decisions

- [ADR-042: Python Migration Strategy](ADR-042-python-migration-strategy.md) (prerequisite, must complete first)
- [ADR-005: PowerShell-Only Scripting](ADR-005-powershell-only-scripting.md) (superseded by ADR-042)
- [ADR-006: Thin Workflows, Testable Modules](ADR-006-thin-workflows-testable-modules.md) (still applies to CI templates)

## References

- [Plugin Marketplace Research](../analysis/claude-code-plugin-marketplaces.md) (session 1180)
- [v0.4.0 Plan](../projects/v0.4.0/PLAN.md)
- [6-Agent Review Debate Log](../critique/ADR-045-debate-log.md)
- [Security Review](../security/ADR-045-framework-extraction-security-review.md)
- [Feasibility Analysis](../analysis/adr-045-feasibility-analysis.md)
- [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins)
- [Claude Code Marketplace Docs](https://code.claude.com/docs/en/plugin-marketplaces)

---

## Amendment Log

| Date | Change | Trigger |
|------|--------|---------|
| 2026-02-07 | Initial proposal | Session 1180 research |
| 2026-02-07 | Revision addressing 9 P0 + 4 P1 issues from 6-agent review | Debate log Round 1 |
