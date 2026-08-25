---
id: ADR-052
status: accepted
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: [ADR-036]
superseded-by: null
explainer: null
implemented: false
---

# ADR-052: Template Strategy for Multi-Platform Agent Distribution

## Status

**Accepted (2026-08-25) as the target architecture.** Supersedes ADR-036. Recorded via owner authorization plus the 6-agent `adr-review` debate at `.agents/critique/ADR-052-debate-log.md`, resolving the dangling supersession issue #5192 opened against this pair.

**Not implemented.** All three Migration Plan phases below are outstanding: no `build/scripts/generate_platform_agents.py` exists, no `platform-overrides/` directory exists. Until Phase 2 of this plan merges, `templates/agents/*.shared.md` (31 files) remains the generator source for `src/copilot-cli/agents/` and `src/vs-code-agents/`, and ADR-036's manual dual-edit procedure remains the operating procedure every contributor and agent follows: see ADR-036's Status for the specific live artifacts. **Do not delete `templates/agents/`, retire `build/generate_agents.py`, or relax any parity or drift gate on the authority of this status line alone.** The authority to change the pipeline arrives with a merged Phase 1/2 implementation, not with this acceptance. Implementation is tracked at issue #5282 (successor to #124, which closed once this ADR's text merged and never tracked delivery).

This acceptance does not contest ADR-036 §Intentional Divergence (the reading that 2-13% Claude-to-template similarity reflects deliberate platform differentiation, not sync failure). See the note under "Evidence of Failure" below.

## Author

rjmurillo-bot (autonomous session, Issue #124)

## Date

2026-03-01

## Prior Art

ADR-036 (Two-Source Agent Template Architecture, 2026-01-01) established the current two-source system: `src/claude/` as the hand-maintained, non-generated Claude source, and `templates/agents/*.shared.md` as the shared source that generates Copilot CLI and VS Code variants only. **Correction (2026-08-25, from the adr-review debate on this acceptance): ADR-036 never claimed Claude Code agents were generated from templates: ADR-036 §Source 1: Claude-Specific states plainly that `src/claude/` files "are the authoritative source for Claude" and are "Not Generated" (a line-number citation here would drift the next time either file's frontmatter changes, as happened once already in this same change).** The similarity table below measures Claude-to-template divergence, a comparison ADR-036 itself never promised would converge; ADR-036 §Intentional Divergence (added 2026-01-01, before this ADR's evidence table) reads that same divergence as deliberate platform differentiation, not sync failure, and this ADR does not overrule that reading (see the note under "Evidence of Failure").

What this ADR actually replaces is narrower than the original text claimed: not "Claude was templated and drifted," since ADR-036 never promised that convergence in the first place, but "the templates/agents/ layer that generates Copilot CLI and VS Code variants adds a maintenance surface without adding synchronization value for that specific purpose" (the same point made under "Evidence of Failure" below). ADR-052 replaces the template-first Copilot/VS Code generation model with a Claude-first one that formalizes Claude's existing canonical role.

## Context

The project distributes agent prompts to three platforms: Claude Code, VS Code (Copilot Chat), and Copilot CLI. The current system uses a three-layer architecture:

1. **Shared templates** in `templates/agents/*.shared.md` (21 files at this ADR's authoring date, 2026-03-01; 31 as of 2026-08-25)
2. **Claude Code agents** in `src/claude/` (23 files at authoring; ~32 as of 2026-08-25, source of truth)
3. **VS Code / Copilot CLI agents** generated from templates in `src/vs-code-agents/` and `src/copilot-cli/`

The repository has also since grown two additional hand-or-generated agent surfaces this ADR's Migration Plan does not account for: `.claude/agents/` and `.github/agents/` (see `build/AGENTS.md:240`). The Migration Plan below targets the four-surface topology as it stood on 2026-03-01; re-scoping against the current six surfaces is tracked at issue #5282 and must happen before Phase 1 executes.

A drift detection script (`build/scripts/detect_agent_drift.py`) compares Claude agents against VS Code and Copilot CLI variants using Jaccard similarity on word tokens across 16 named sections.

### Evidence of Failure

A 2025-12-15 analysis (`.agents/analysis/drift-analysis-claude-vs-templates.md`) measured similarity between Claude agents and shared templates:

| Agent | Similarity | Gap |
|-------|-----------|-----|
| independent-thinker | 2.4% | 97.6% |
| high-level-advisor | 3.8% | 96.2% |
| critic | 9.7% | 90.3% |
| task-decomposer | 11.9% | 88.1% |
| architect | 12.6% | 87.4% |
| milestone-planner | 12.8% | 87.2% |

Templates and Claude agents share between 2-13% content.

**Note (2026-08-25, adr-review debate):** ADR-036 §Intentional Divergence reads this same range as deliberate platform differentiation, not a synchronization defect: "Historical drift analysis showing 2-12% similarity between Claude and templates reflects this intentional platform differentiation, not maintenance failure." This ADR's acceptance does not overrule that reading: Claude was never meant to converge with the shared templates under either architecture. What this ADR's evidence actually supports is narrower: the shared-template layer's sole functional purpose is generating the Copilot CLI and VS Code variants, and a direct Claude-to-platform transformation removes an intermediate representation that added a maintenance surface without adding synchronization value for that purpose.

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
- Verdict: **Rejected.** The template layer earns its cost only if it delivers the synchronization it claims to. For its actual purpose (generating Copilot CLI/VS Code from a shared source), it demonstrably has not. This verdict does not rest on the Claude-to-template similarity figures below, which ADR-036 §Intentional Divergence already reads as deliberate, not as evidence of failure; see "Evidence of Failure" for that distinction.

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

- Removes the shared template files (21 at authoring, 31 as of 2026-08-25), whose only measurable purpose (generating Copilot CLI/VS Code variants) is served more directly by generating straight from `src/claude/`
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

**Rollback**: If Phase 2 verification fails, restore templates from git history (`git checkout HEAD~1 -- templates/agents/`) and revert CI workflow changes. Template files remain recoverable from version control indefinitely.

### Phase 3: Override Mechanism

1. Create `platform-overrides/` for per-agent, per-platform customizations
2. Document override format in contributing guide
3. Add CI validation that overrides do not diverge from Claude base beyond tool/frontmatter sections

## Confirmation

**Target state: describes CI once Phase 1-3 are implemented, not current behavior.** As of 2026-08-25, `build/scripts/detect_agent_drift.py`'s module docstring explicitly excludes `src/copilot-cli/agents` and `templates/agents` from its comparison and states Claude agents "are NOT generated from templates"; the live drift-compared pairs are `src/claude` vs `src/vs-code-agents` and `.claude/agents` vs `.github/agents`. Cited by docstring, not line range, for the same reason ADR-036's Prior Art citation above moved to a section name. Once implemented, compliance will be verified through CI:

1. `build/scripts/detect_agent_drift.py` compares generated VS Code and Copilot CLI agents against Claude source. Drift beyond frontmatter and tool declarations fails the build.
2. The generation script (`generate_platform_agents.py`) runs in CI on every push to ensure derived agents stay current.
3. Any manual edit to `src/vs-code-agents/` or `src/copilot-cli/` triggers a drift warning because those directories contain generated output.

## Implementation Status

- [ ] Phase 1: Create `build/scripts/generate_platform_agents.py`
- [ ] Phase 2: Verify generated output and remove `templates/agents/`
- [ ] Phase 3: Create `platform-overrides/` mechanism

No blockers identified in the original 2026-03-01 scope; the plan itself needs re-scoping against the current six-surface agent topology before Phase 1 starts (see Context above). Implementation tracked via issue #5282: issue #124 (this ADR's original tracker) closed 2026-03-01 once this ADR's text merged and never tracked delivery.

## Security Considerations

This ADR affects documentation and build tooling only. No runtime behavior, authentication, data handling, or network exposure changes. The generation script processes local markdown files with no external inputs.

## References

- Issue #124 (closed 2026-03-01, decision-only): Strategic decision needed on dual template system
- Issue #5282 (open): implement this ADR's migration, re-scoped against six agent surfaces
- ADR-036: Two-Source Agent Template Architecture (superseded by this ADR; still operative pending migration)
- `.agents/critique/ADR-052-debate-log.md`: 6-agent adr-review debate recording this acceptance
- `.agents/analysis/drift-analysis-claude-vs-templates.md`
- `.agents/analysis/template-strategy-debate.md` (architect review findings)
- `.agents/retrospective/2025-12-15-accountability-analysis.md`
- `build/scripts/detect_agent_drift.py`
- ADR-042: Python for new scripts (applies to `generate_platform_agents.py`)
- ADR-044: Copilot CLI frontmatter compatibility
