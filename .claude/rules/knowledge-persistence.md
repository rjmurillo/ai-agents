---
paths:
  - "**"
priority: high
---

# Knowledge Persistence Rule

When you learn a durable fact, convention, or decision procedure that future sessions must honor, choose the persistence surface by who must obey it and across which harnesses. This repository runs under Claude, Codex, and Copilot. A convention that lives in only one harness's memory is invisible to the other two.

## Decision procedure

1. **Ephemeral, this-task-only**: do not persist as a rule. Record it in the session log if it matters for the handoff.
2. **Retrieval aid, non-binding**: Serena memory (`.serena/memories/`, committed but MCP-gated) or Copilot Memory (the `store_memory` tool, GitHub-scoped and per-user). Use these for "useful to recall," never as the binding for a convention other harnesses must follow. Serena is not guaranteed loaded on every harness; Copilot Memory does not reach Claude or Codex at all.
3. **Durable convention that binds every contributor and every harness**: a rule file under `.claude/rules/<name>.md`. This is the canonical surface.

## MUST

1. **Canonical rule lives in `.claude/rules/`**. A convention that must bind across Claude, Codex, and Copilot MUST be written to `.claude/rules/<name>.md`, not only to Serena memory or Copilot Memory. `AGENTS.md` directs every harness to read `.claude/rules/*.md` first, so Claude (reads the tree directly) and Codex (reads `AGENTS.md`) both resolve to it, and Copilot reads the generated mirror.
2. **Regenerate the mirrors in the same change**. Adding or editing a `.claude/rules/*.md` file MUST regenerate `.github/instructions/<name>.instructions.md` and `src/copilot-cli/instructions/<name>.instructions.md` with `build/scripts/generate_rules.py`, committed in the same change. A stale mirror is torn state (see `.claude/rules/generated-artifacts.md`).
3. **Bump the plugin manifests**. `.claude/` and `src/copilot-cli/` ship in the project-toolkit plugin, so a rule change MUST bump both `.claude-plugin/plugin.json` manifests to the same strictly-greater version (see `.claude/rules/plugin-version-bump.md`, parity gate). One bump covers all rule changes in the same PR.
4. **Scope by `paths:`**. Set `paths:` to the narrowest glob that fires where the convention applies (`tests/**`, `**/*.ps1`). A universally-binding convention sets `paths: ["**"]`.

## SHOULD

1. **Prefer an existing rule file**. Before adding a new `.claude/rules/*.md`, SHOULD add the item to the closest existing rule (a testing convention to `.claude/rules/testing.md`, a security convention to `.claude/rules/security.md`). Create a new file only when no existing rule owns the concern.
2. **Cite the incident**. SHOULD name the failure, PR, or review that motivated the convention, so the next reader can weigh it (mirrors `.claude/rules/governance.md` "Evidence required").

## MUST NOT

1. MUST NOT rely on Serena memory or Copilot Memory alone to persist a convention that other harnesses or contributors must obey. Those are retrieval complements, not the cross-harness binding.
2. MUST NOT hand-edit a generated mirror under `.github/instructions/` or `src/copilot-cli/instructions/`. Edit the canonical rule and regenerate.

## References

- `AGENTS.md`. Directs every harness to read `.claude/rules/*.md` by `applyTo` first; the Codex common denominator.
- `build/scripts/generate_rules.py`. Generates both instruction mirrors from `.claude/rules/`.
- `.claude/rules/generated-artifacts.md`. Regenerate-and-commit-in-the-same-change discipline.
- `.claude/rules/plugin-version-bump.md`. Parity and strictly-greater bump gates.
- `.claude/rules/canonical-source-mirror.md`. Load-bearing "mirrors" claims must cite and quote the source.
