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

What this ADR actually replaces is narrower than the original text claimed: not "Claude was templated and drifted," since ADR-036 never promised that convergence in the first place. **Correction (2026-08-25, review): the templates layer does deliver synchronization value today.** `build/generate_agents.py` (module docstring, lines 4-6) reads `templates/agents/*.shared.md` as the single source generating both the VS Code and Copilot CLI outputs, and CI validates the generated output against that source, so the two derived platforms are kept in sync by construction, not merely in theory. What this ADR actually argues is narrower still: a Claude-first transformation can preserve that same generated-and-validated synchronization for VS Code and Copilot CLI while removing one source layer, going directly from `src/claude/` to the two derived outputs instead of from `templates/agents/` to the two derived outputs, dropping the maintenance surface from three trees (templates, Claude, derived) to two (Claude, derived). ADR-052 replaces the template-first Copilot/VS Code generation model with a Claude-first one that formalizes Claude's existing canonical role.

## Context

The project distributes agent prompts to three platforms: Claude Code, VS Code (Copilot Chat), and Copilot CLI. The current system uses a three-layer architecture:

1. **Shared templates** in `templates/agents/*.shared.md` (21 files at this ADR's authoring date, 2026-03-01; 31 as of 2026-08-25)
2. **Claude Code agents** in `src/claude/` (23 files at authoring; ~32 as of 2026-08-25, source of truth)
3. **VS Code / Copilot CLI agents** generated from templates in `src/vs-code-agents/` and `src/copilot-cli/`

The repository has also since grown two additional hand-or-generated agent surfaces this ADR's Migration Plan does not account for: `.claude/agents/` and `.github/agents/` (see `build/AGENTS.md:240`). The Migration Plan below targets the four-surface topology as it stood on 2026-03-01; re-scoping against the current six surfaces is tracked at issue #5282 and must happen before Phase 1 executes.

A drift detection script (`build/scripts/detect_agent_drift.py`) compares Claude agents against VS Code variants (and separately, the `.claude/agents`/`.github/agents` install copies) using Jaccard similarity on word tokens across a named-section allowlist. **Correction (2026-08-25, review): the script does not compare against Copilot CLI agents at all** (module docstring, lines 4-33): `src/copilot-cli/agents` is held to an exact string match against its template source by `generate_agents.py --validate` instead. The allowlist currently has 23 entries, not 16; both figures are volatile and should be re-measured against the live script rather than trusted from this ADR.

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

**Note (2026-08-25, adr-review debate):** ADR-036 §Intentional Divergence reads this same range as deliberate platform differentiation, not a synchronization defect: "Historical drift analysis showing 2-12% similarity between Claude and templates reflects this intentional platform differentiation, not maintenance failure." This ADR's acceptance does not overrule that reading: Claude was never meant to converge with the shared templates under either architecture. **Correction (2026-08-25, review): the shared-template layer does currently deliver the synchronization it exists for**, per `build/generate_agents.py` (see the correction under "Prior Art" above). **Second correction (2026-08-25, review): the layer has a third live consumer this ADR's evidence omitted.** `build/generate_agent_catalog.py` also reads `templates/agents/*.shared.md` as its system of record and emits `docs/agent-catalog.md`, wired into `build/scripts/build_all.py` as a separate `agent-catalog` generator step from the two agent outputs. What this ADR's evidence actually supports is narrower still: the shared-template layer's functional purpose is generating the Copilot CLI variant, the VS Code variant, and the agent catalog, and a direct Claude-to-platform transformation can deliver the same synchronization for the first two with one fewer source, but the catalog generator needs its own migration step: see the Migration Plan's Phase 2 note below.

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
- Verdict: **Rejected.** **Correction (2026-08-25, review): not on a synchronization failure.** `build/generate_agents.py` generates and CI validates both platform outputs from `templates/agents/*.shared.md` today, so the template layer does deliver the synchronization it claims to for its stated purpose (generating Copilot CLI/VS Code from a shared source). **The layer also feeds `build/generate_agent_catalog.py`, which reads the same templates as the system of record for `docs/agent-catalog.md`** (Copilot, PR #5286); a plan that removes `templates/agents/` without a replacement source for that generator breaks a live output, not a redundant one. The rejection rests instead on cost: keeping a third tree (templates) alongside `src/claude/` and the derived outputs is a duplicate-source maintenance surface that a direct Claude-to-platform transformation can remove without losing the agent-synchronization property, provided the catalog generator is migrated in the same change rather than left pointing at a deleted directory (see the Migration Plan's Phase 2 note below). This verdict does not rest on the Claude-to-template similarity figures below, which ADR-036 §Intentional Divergence already reads as deliberate, not as evidence of failure; see "Evidence of Failure" for that distinction.

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
2. The template layer adds a maintenance surface (correction, 2026-08-25 review: it does deliver its intended synchronization today, per `build/generate_agents.py`) that a direct Claude-to-platform transformation can eliminate without losing that synchronization property.
3. A Claude-to-platform transformation is simpler than template-to-platform generation because it eliminates the intermediate representation.
4. The drift detection script already operates on the correct model for the pairs it covers today (`src/claude` vs `src/vs-code-agents`, and `.claude/agents` vs `.github/agents`, both compared against Claude source); it does not yet cover `src/copilot-cli/agents`, which today is held to an exact-match generator check instead (see the correction under "Prior Art").

## Consequences

### Positive

- Removes the shared template files (21 at authoring, 31 as of 2026-08-25), whose two outputs (generating Copilot CLI/VS Code variants) are served more directly by generating straight from `src/claude/`; the third output, `docs/agent-catalog.md`, needs a replacement source in the same migration (see Migration Plan Phase 2)
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
2. **Retire `build/generate_agents.py`'s `templates/agents/*.shared.md` dependency.** It exits 1 on zero shared files (`generate_agents.py:223-225`), so removing the directory before this step reds the build; this generator's own retirement was implied by this ADR's Status section but not previously sequenced here.
3. **Migrate `build/generate_agent_catalog.py` off `templates/agents/*.shared.md`.** As of 2026-08-25 that generator treats the template tree as `docs/agent-catalog.md`'s system of record and is wired into `build/scripts/build_all.py` as its own `agent-catalog` step, independent of the two agent-output generators (Copilot, PR #5286). **Correction (2026-08-25, Round 3 adr-review): the target this step originally prescribed, "point it at `src/claude/*.md` and verify `docs/agent-catalog.md` regenerates unchanged," is not reachable as written** (independent-thinker and critic, Round 3): `src/claude/*.md` carries `role:` nested under a `metadata:` key rather than at top level (only 6 of 33 files have a top-level `role:`), and none carry the `name:` field the templates provide; `generate_agent_catalog.py:159-172` raises `CatalogError` on a missing top-level `role`. The catalog renderer also hardcodes `../templates/agents/{name}.shared.md` links that would point at the deleted tree. Whoever executes this phase must resolve the source-shape mismatch first (either add a compatible frontmatter shim or adjust the generator to read `src/claude/`'s actual schema) and expect a reviewed diff, not byte-for-byte parity.
4. **`build/scripts/build_all.py` silently, not loudly, skips catalog generation when the source directory is absent** (`_build_agent_catalog`, `build_all.py:143-146`, exit 0 with a notice). **Correction (2026-08-25, Round 3 adr-review): this alone does not mask the break** (architect, analyst, security, Round 3): `scripts/validation/validate_agent_catalog.py` is a separate pre-PR gate that fails closed (exit 2) on a missing `templates/agents/` directory, wired as a hard-failing check in `scripts/validation/checks_spec.py`. Deletion-before-migration would be caught there, loudly, before merge; `build_all.py`'s own silence is real but is not the last line of defense.
5. Remove `templates/agents/` directory
6. Update `build/scripts/detect_agent_drift.py` to compare against Claude source directly
7. **Update every live consumer of `templates/agents/`, not only the two named CI workflows** (architect and independent-thinker, Round 3, found this enumeration incomplete twice): `lefthook.yml`'s `generate-agent-catalog` job (a local hook, not a CI workflow), `scripts/validation/check_skill_md_portability.py` (`EXTRA_SCAN_ROOTS`), and `check_agent_skill_discriminator.py` plus its `.github/workflows/agent-skill-discriminator-check.yml` wiring. Re-audit for any further reader before executing this phase; the pattern of finding one more consumer per review round suggests the current list is still not exhaustive.
8. **Measure the actual maintenance-surface change before claiming a reduction.** This ADR's Consequences section claims "3 trees to 2," but the migration destination (`src/claude/`, ~33 files) is not a clean superset of the source (`templates/agents/`, 31 files): different frontmatter shape, different file count. Produce a real before/after surface measurement in issue #5282 rather than treating "3 to 2" as a settled fact (high-level-advisor, Round 3).

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
