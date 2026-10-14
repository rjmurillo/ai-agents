---
paths:
  - "templates/**"
priority: high
---

# Template File Rules

`templates/` is the source of truth for every agent copy (ADR-109). `build/scripts/agent_templates.py` renders each `<stem>.claude.md.tmpl` into `src/claude/agents/`, `build/generate_agents.py` writes the Copilot CLI, VS Code, and GitHub trees from the `<stem>.copilot.md.tmpl` side, and the binplace step copies `src/claude/agents/` onto `.claude/agents/`. One `build_all.py` run does all of it. Edit the template, never a rendered copy.

<!-- vendor-portability: this rule names contributor-facing regeneration
commands (`build/generate_agents.py`, `build/scripts/build_all.py`) under the
upstream-only `build/` tree, absent from every vendored plugin install. A
consumer never runs either; the mentions are dev workflow, not runtime
instructions the shipped skill would execute. Issue #2050. -->

## MUST

1. **Regenerate after edits**. Changes MUST be followed by running the one command `.claude/rules/knowledge-persistence.md` documents before commit. Uncommitted generator output is a protocol failure.

   ```bash
   uv run python build/scripts/build_all.py
   ```

   `build_all.py` compiles the agent, rule, skill, and hook templates, regenerates the platform and Copilot mirrors, and binplaces `.claude/`, in one run (ADR-108, ADR-109). `build/generate_agents.py` alone does not compile the `.claude.md.tmpl` and `.copilot.md.tmpl` pair, so it leaves `src/claude/agents/` and `.claude/agents/` stale.
2. **Commit generated output**. Every regenerated tree MUST be committed in the same PR as the template change: `src/claude/agents/`, `.claude/agents/`, `.github/agents/`, `src/copilot-cli/agents/`, and `src/vs-code-agents/`. `.agents/governance/GENERATOR-FILES.md` lists each generator and its output.
3. **Toolset integrity**. Changes that add or remove tools MUST update `templates/toolsets.yaml` consistently.
4. **Frontmatter fields**. Agent templates MUST keep `description` present and valid. `name` lives in each `.claude.md.tmpl` only. The `.copilot.md.tmpl` and `.shared.md` files omit it: the generator derives the Copilot-side name from the template filename before platform conversion and adds it only for a platform whose config sets `includeNameField: true`. `model_tier` is optional: ADR-111 (which supersedes ADR-080) governs whether a generated agent may carry a `model:` pin at all (see MUST-5).
5. **Model selection**. A template's `model_tier` MUST comply with ADR-111. The generator resolves a `model:` pin for the generated Copilot/VS Code/Visual Studio mirrors in two cases only: a fresh, fully-validated `KEEP_PIN` entry in the ADR-111 sidecar manifest for that template (ADR-111 rules 2 and 4, any tier), or the `haiku` tier with no such entry, the sole cost exception ADR-111 rule 3 recognizes. When no valid manifest entry exists, `model_tier: opus` or `model_tier: sonnet`, and no `model_tier` at all, MUST resolve to no `model:` field, so the mirror inherits the harness default rather than shipping an unjustified pin that breaks on the next model retirement (issue #5313).
6. **Sync the lossless fixture and offset every added byte**. After `build_all.py`, copy `src/claude/rules/<name>.md` over `tests/build_scripts/fixtures/rule_templates_b2/expected/<name>.md`, or the `Rule Lossless Fixtures` gate in `pre_pr.py` fails. Instruction Bytes fixture F2 sits at its 220000 ceiling and its ratchet test forbids a raise, so trim the same rule by every byte you add, portability markers included.
7. **Keep a skill template inside its gates**. A rendered `SKILL.md` caps at 500 lines and 24576 bytes, and Instruction Bytes fixtures F1 to F6 count its `depends-on` closure with little headroom. Put procedure in `references/*.md`. Route a new skill with `metadata.routing.intents`, without growing the always-on corpus or an autoplan table row.

## SHOULD

1. **Minimal diff**. Template edits SHOULD make one logical change at a time; avoid bundling prompt rewrites with toolset changes.
2. **Preview per platform**. SHOULD inspect the generated output for both target platforms (`src/copilot-cli/agents/<agent>.agent.md` and `src/vs-code-agents/<agent>.agent.md`) to confirm the change renders correctly.
3. **Check drift detection**. SHOULD run `uv run python build/scripts/detect_agent_drift.py` after generation. It does NOT compare templates against anything; it scores `src/claude/agents` against `src/vs-code-agents`, and `.claude/agents` against `.github/agents`, over the 23 sections in `SECTIONS_TO_COMPARE`, so green does not show your template edit reached every copy. Run `build_all.py --check` for that.

## MUST NOT

1. MUST NOT edit generated files directly (`src/claude/agents/`, `.claude/agents/`, `.github/agents/`, `src/copilot-cli/agents/`, `src/vs-code-agents/`). Edit the template in `templates/` and regenerate; the claude-agents rule, MUST-1, says the same.
2. MUST NOT remove a platform target without a corresponding ADR.

## Compose a capability, do not copy its policy

Before you write a normative block into a template, check whether some artifact
already owns that policy. A capability has exactly one canonical owner, and
every other artifact declares a dependency on it instead of restating it.

Declare it in the artifact's own frontmatter, nested under `metadata`:

```yaml
metadata:
  capability:
    kind: orchestrator | specialized-implementation | reusable-primitive | cross-cutting-rule
    owns: [capability-name]
    depends-on: [capability-name]
    status: active
```

One declaration site per class: a skill declares in its SKILL.md template, a
rule in its Markdown file, and an agent in its shared body rather than either
per-harness template. A policy a prompt must carry at runtime renders in
through a partial; a policy a reader only needs to find is cited.

The gate refuses a dependency that resolves to no owner, two owners for one
capability, a cycle, and a consumer that repeats three or more consecutive
lines of the owner it depends on. It runs in the pre-PR sequence, so a broken
edge fails before review. ADR-110 carries the contract and names the gate.

## References

- `build/generate_agents.py`. Canonical generator
- `.project-toolkit/architecture/ADR-111-skill-model-pins-project-per-harness.md`. Model pin policy (supersedes ADR-080)
- `.agents/steering/agent-prompts.md`. Prompt authoring standards
- `templates/README.md`. Template structure
