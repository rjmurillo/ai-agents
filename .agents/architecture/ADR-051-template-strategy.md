# ADR-051: Template Strategy for Multi-Platform Agent Distribution

## Status

Proposed

## Date

2026-03-01

## Context

The project distributes agent prompts to three platforms: Claude Code, VS Code (Copilot Chat), and Copilot CLI. The current system uses a three-layer architecture:

1. **Shared templates** in `templates/agents/*.shared.md` (21 files)
2. **Claude Code agents** in `src/claude/` (23 files, source of truth)
3. **VS Code / Copilot CLI agents** generated from templates in `src/vs-code-agents/` and `src/copilot-cli/`

A drift detection script (`build/scripts/detect_agent_drift.py`) compares Claude agents against VS Code and Copilot CLI variants using Jaccard similarity on word tokens across 16 named sections.

### Evidence of Failure

A 2025-12-15 analysis (`.agents/analysis/drift-analysis-claude-vs-templates.md`) measured similarity between Claude agents and shared templates:

| Agent | Similarity | Gap |
|-------|-----------|-----|
| independent-thinker | 2.4% | 97.6% |
| high-level-advisor | 3.8% | 96.2% |
| critic | 9.7% | 90.3% |
| task-generator | 11.9% | 88.1% |
| architect | 12.6% | 87.4% |
| planner | 12.8% | 87.2% |

Templates and Claude agents share between 2-13% content. The template layer adds maintenance cost without delivering synchronization value.

### Platform Differences

Each platform requires different frontmatter and tool declarations:

- **Claude Code**: `name:`, `model:`, Claude Code Tools section with MCP tool syntax
- **VS Code**: `tools:` array with VS Code tool names, `model: Claude Opus 4.5`
- **Copilot CLI**: Similar to VS Code with `(copilot)` model suffix

The prompt body (Core Identity, Responsibilities, Constraints, Handoff) can be shared. The wrapper (frontmatter, tool access, platform syntax) cannot.

## Decision

**Option B: Claude-First**. Claude Code agents are the canonical source. VS Code and Copilot CLI agents are derived from Claude agents through a transformation script.

### Options Evaluated

#### Option A: Template-First (Current)

All changes start in shared templates. Platform variants are generated.

- Pro: Single source of truth in theory
- Con: Templates diverged 88-98% from Claude agents. The "source of truth" is neither maintained nor enforced. Two maintenance surfaces (templates AND Claude agents) with no synchronization guarantee.
- Verdict: **Rejected.** Data shows the template layer is fiction. Maintaining it creates work with no measurable value.

#### Option B: Claude-First (Selected)

Claude Code agents are canonical. A build script extracts the shared prompt body and wraps it in platform-specific frontmatter for VS Code and Copilot CLI.

- Pro: Eliminates the template layer. Reduces maintenance surfaces from 3 to 2 (Claude source + generation script). Claude is already the most-used platform and receives the most iteration.
- Con: Platform-specific features for VS Code or Copilot CLI require either per-platform overrides or conditional sections in Claude agents.
- Mitigation: Platform differences are limited to frontmatter and tool declarations. A `platform-overrides/` directory can hold per-agent, per-platform patches when needed.

#### Option C: Independent Platforms

Each platform maintains its own agents. No generation, no synchronization.

- Pro: Maximum flexibility per platform.
- Con: Drift is guaranteed. Core Identity and behavioral changes must be manually replicated across 3 x 21 = 63 files. The 2025-12-15 retrospective showed agents already failed to maintain consistency with automated tooling. Manual sync would perform worse.
- Verdict: **Rejected.** Scales maintenance linearly with platform count. Drift is inevitable.

### Rationale

1. Claude agents are already the source of truth. This formalizes existing practice.
2. The template layer adds a maintenance surface that has demonstrated zero synchronization value.
3. A Claude-to-platform transformation is simpler than template-to-platform generation because it eliminates the intermediate representation.
4. The drift detection script already operates on the correct model (comparing derived variants against Claude source).

## Consequences

### Positive

- Removes 21 shared template files that diverged 88-98% from actual agents
- Reduces maintenance surfaces from 3 (templates, Claude, derived) to 2 (Claude, derived)
- Makes the source of truth explicit and enforceable
- Simplifies drift detection (compare derived against Claude, no template intermediary)

### Negative

- Platform-specific features require an override mechanism rather than template parameterization
- Contributors must understand that `src/claude/` is canonical and other platform directories are generated

## Migration Plan

### Phase 1: Script Creation

Create `build/scripts/generate_platform_agents.py` that:

1. Reads each Claude agent from `src/claude/`
2. Extracts the prompt body (everything after Claude-specific frontmatter and tool sections)
3. Wraps in VS Code frontmatter (from `platform-overrides/vscode.yml` defaults)
4. Wraps in Copilot CLI frontmatter (from `platform-overrides/copilot-cli.yml` defaults)
5. Writes to `src/vs-code-agents/` and `src/copilot-cli/`

### Phase 2: Template Removal

1. Verify generated output matches current VS Code and Copilot CLI agents (or improves on them)
2. Remove `templates/agents/` directory
3. Update `build/scripts/detect_agent_drift.py` to compare against Claude source directly
4. Update CI workflows that reference template paths

### Phase 3: Override Mechanism

1. Create `platform-overrides/` for per-agent, per-platform customizations
2. Document override format in contributing guide
3. Add CI validation that overrides do not diverge from Claude base beyond tool/frontmatter sections

## References

- Issue #124: Strategic decision needed on dual template system
- `.agents/analysis/drift-analysis-claude-vs-templates.md`
- `.agents/retrospective/2025-12-15-accountability-analysis.md`
- `build/scripts/detect_agent_drift.py`
- ADR-044: Copilot CLI frontmatter compatibility
