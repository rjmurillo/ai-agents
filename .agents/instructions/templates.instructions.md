---
applyTo: "templates/**"
priority: high
---

# Template File Rules

`templates/` is the source of truth for generated platform artifacts. A change here cascades to every harness (Claude, Copilot, Cortex, Factory Droid) via the generator. Forgetting to regenerate leaves the platforms out of sync.

## MUST

1. **Regenerate after edits** — Changes MUST be followed by running `python3 build/generate_agents.py` (or the equivalent `Generate-Agents.ps1`) before commit. Uncommitted generator output is a protocol failure.
2. **Commit generated output** — Regenerated files under `src/claude/`, `.github/agents/`, and similar target directories MUST be committed in the same PR as the template change.
3. **Toolset integrity** — Changes that add or remove tools MUST update `templates/toolsets.yaml` consistently.
4. **Frontmatter fields** — Agent templates MUST keep required YAML frontmatter fields (`name`, `description`, `model`) present and valid per ADR-002.
5. **Model selection** — Model choices MUST match ADR-002 (`opus` / `sonnet` / `haiku` assignments).

## SHOULD

1. **Minimal diff** — Template edits SHOULD make one logical change at a time; avoid bundling prompt rewrites with toolset changes.
2. **Preview per platform** — SHOULD inspect the generated output for at least two platforms (e.g., `src/claude/<agent>.md` and `.github/agents/<agent>.md`) to confirm the change renders correctly.
3. **Check drift detection** — SHOULD run the drift-detection script (`scripts/validation/agent_drift` if present) after generation.

## MUST NOT

1. MUST NOT edit generated files directly (`src/claude/`, `.github/agents/`). Edit the template in `templates/` and regenerate.
2. MUST NOT remove a platform target without a corresponding ADR.

## References

- `build/generate_agents.py` — canonical generator
- `.agents/architecture/ADR-002-agent-model-selection-optimization.md` — model assignments
- `.agents/steering/agent-prompts.md` — prompt authoring standards
- `templates/README.md` — template structure
