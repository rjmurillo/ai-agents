---
applyTo: templates/**
---

# Template File Rules

`templates/` is the source of truth for the agent copies that `build/generate_agents.py` writes: `src/copilot-cli/agents/` and `src/vs-code-agents/`. It does NOT cascade everywhere. `src/claude/`, `.claude/agents/`, and `.github/agents/` are hand-maintained and no generator writes them, so a template edit reaches them only if you make the matching edit yourself in the same change. Forgetting either half leaves the platforms out of sync.

## MUST

1. **Regenerate after edits**. Changes MUST be followed by running `uv run python build/generate_agents.py` before commit. Uncommitted generator output is a protocol failure.
2. **Commit generated output**. Regenerated files under `src/copilot-cli/agents/` and `src/vs-code-agents/` MUST be committed in the same PR as the template change. Those two are the only trees `build/generate_agents.py` writes; `src/claude/`, `.claude/agents/`, and `.github/agents/` are hand-maintained and the generator does not touch them (see `.agents/governance/GENERATOR-FILES.md`).
3. **Toolset integrity**. Changes that add or remove tools MUST update `templates/toolsets.yaml` consistently.
4. **Frontmatter fields**. Agent templates MUST keep `description` present and valid. `name` is not a template field: no shipped agent template defines it, and the generator derives the generated agent's name from the template's own filename before platform conversion, adding it back only for a platform whose config sets `includeNameField: true`. `model_tier` is optional: ADR-080 governs whether a generated agent may carry a `model:` pin at all (see MUST-5). ADR-002, formerly cited here, is deprecated in favor of ADR-080 (2026-08-25).
5. **Model selection**. A template's `model_tier` MUST comply with ADR-080: the generator resolves only the `haiku` tier, the sole cost exception ADR-080 rule 3 recognizes, into a versioned `model:` pin for the generated Copilot/VS Code/Visual Studio mirrors. `model_tier: opus` or `model_tier: sonnet`, and no `model_tier` at all, MUST resolve to no `model:` field, so the mirror inherits the harness default rather than shipping an unjustified pin that breaks on the next model retirement (issue #5313).

## SHOULD

1. **Minimal diff**. Template edits SHOULD make one logical change at a time; avoid bundling prompt rewrites with toolset changes.
2. **Preview per platform**. SHOULD inspect the generated output for both target platforms (`src/copilot-cli/agents/<agent>.agent.md` and `src/vs-code-agents/<agent>.agent.md`) to confirm the change renders correctly.
3. **Check drift detection**. SHOULD run `python3 build/scripts/detect_agent_drift.py` after generation. Read its scope first: it does NOT compare templates against anything. It scores `src/claude` against `src/vs-code-agents`, and `.claude/agents` against `.github/agents`, over an 18-section allowlist, so a green run is not evidence that your template edit reached the hand-maintained copies. See the claude-agents rule.

## MUST NOT

1. MUST NOT edit generated files directly (`src/copilot-cli/agents/`, `src/vs-code-agents/`). Edit the template in `templates/` and regenerate. This does NOT apply to `src/claude/`, `.claude/agents/`, or `.github/agents/`, which are hand-maintained; the claude-agents rule, MUST-1, requires editing `src/claude/<agent>.md` directly, in the same change as the template.
2. MUST NOT remove a platform target without a corresponding ADR.

## References

- `build/generate_agents.py`. Canonical generator
- `.agents/architecture/ADR-080-model-pin-justification-policy.md`. Model pin policy (supersedes ADR-002's method, per ADR-002's own 2026-08-25 deprecation note)
- `.agents/steering/agent-prompts.md`. Prompt authoring standards
- `templates/README.md`. Template structure
