---
paths:
  - ".claude/rules/**"
  - ".serena/memories/**"
  - ".github/instructions/**"
  - "src/copilot-cli/instructions/**"
priority: high
---

# Knowledge Persistence Rule

This rule covers the mechanics of writing to a persistence surface: rule files, the mirrors generated from them, and Serena memories. It fires when you edit one of those trees.

Choosing which surface a fact belongs on binds earlier, before you know which tree you will open, so that decision procedure lives in the always-on Universal Rules under "Choosing a persistence surface".

## MUST

1. **Canonical rule lives in `.claude/rules/`**. A convention that must bind across Claude, Codex, and Copilot MUST be written to `.claude/rules/<name>.md`, not only to Serena memory or Copilot Memory. `AGENTS.md` directs every harness to read `.claude/rules/*.md` first, so Claude (reads the tree directly) and Codex (reads `AGENTS.md`) both resolve to it, and Copilot reads the generated mirror.
2. **Regenerate the mirrors in the same change**. Adding or editing a `.claude/rules/*.md` file MUST regenerate `.github/instructions/<name>.instructions.md` and `src/copilot-cli/instructions/<name>.instructions.md` with `build/scripts/generate_rules.py`, committed in the same change. A stale mirror is torn state (see `.claude/rules/generated-artifacts.md`).
3. **Leave the plugin manifests alone**. `.claude/` and `src/copilot-cli/` ship in the project-toolkit plugin, but the manifests carry no `version` field: Claude Code resolves freshness from the commit SHA instead, so a rule change needs no manifest edit. Adding a `version` back fails `build/scripts/validate_plugin_version_bump.py` (see `.claude/rules/plugin-version-bump.md` and ADR-092).
4. **Scope by `paths:`**. Set `paths:` to the narrowest glob that fires where the convention applies (`tests/**`, `**/*.ps1`). A universally-binding convention sets `paths: ["**"]`.
5. **Index a new Serena memory by hand**. A memory under `.serena/memories/` MUST get a keyword line in `memory-index.md` in the same change, or keyword retrieval cannot reach it. `memory_index.py --ci` checks only that index rows resolve to files, never the reverse, so nothing catches the omission. Write `(0)` as the token placeholder; the `memory-token-update` pre-commit job rewrites it to the real count.
6. **Repair token counts by hand when the autofix is skipped**. `memory-token-update` carries `skip: [merge, "test $SKIP_AUTOFIX = 1"]`, so a memory edited inside a merge commit, or committed with `SKIP_AUTOFIX=1`, keeps a stale count. Pre-push `memory-index-token-ratchet` then fails and names every stale entry. Fix it by running `uv run --frozen python scripts/update_memory_index_tokens.py`, not by editing the number by hand. Measured on pristine `main` before the ratchet existed: `skills-git-index` recorded 287 against an actual 324, a 13% undercount that merged (Issue #4441).

## SHOULD

1. **Prefer an existing rule file**. Before adding a new `.claude/rules/*.md`, SHOULD add the item to the closest existing rule (a testing convention to `.claude/rules/testing.md`, a security convention to `.claude/rules/security.md`). Create a new file only when no existing rule owns the concern.
2. **Cite the incident**. SHOULD name the failure, PR, or review that motivated the convention, so the next reader can weigh it (mirrors `.claude/rules/governance.md` "Evidence required").

## When to write a Serena memory (tier 2 guidance)

Write a Serena memory when ALL of the following hold:

- The information was derived during this session (observed behavior, a gotcha, a
  project-specific pattern, a decision rationale, a non-obvious codebase fact).
- It is NOT already expressed in an existing rule or Serena memory
  (search existing Serena memories first).
- A future session working on the same area would save 5+ minutes by having it.
- It does NOT need to be a guaranteed binding for every harness and contributor. Serena is
  MCP-gated, so must-obey conventions belong in a rule file instead.

Do NOT write a Serena memory when:

- The same information is already in an existing rule, writing a duplicate
  creates drift if the rule is later updated.
- The convention must bind every harness or every contributor -> use `.claude/rules/` instead.
- The information is ephemeral to this task only (no future session needs it).
- It is trivially re-derivable from the codebase in under a minute.

SHOULD check before writing: search Serena with 2-3 keywords from the insight. If a
memory already covers it, augment the existing entry rather than creating a duplicate.

## Net-new information decision checklist

Before persisting anything, ask in order:

1. **Already covered?** Search existing rules and Serena memories. If yes, augment; do not duplicate.
2. **Re-derivable easily?** If a `Grep` or `Read` would surface it in under a minute, skip.
3. **Required investigation?** If it took failed attempts, non-obvious codebase traversal, or
   cross-file reasoning to arrive at -> persist it.
4. **Which surface?**
   - Binds all harnesses / all contributors -> `.claude/rules/<name>.md` (+ mirrors)
   - Retrieval context, useful to recall -> write a Serena memory
   - Ephemeral / task-only -> neither; session log only if relevant for handoff

## MUST NOT

1. MUST NOT hand-edit a generated mirror under `.github/instructions/` or `src/copilot-cli/instructions/`. Edit the canonical rule and regenerate.

Three further MUST NOT items moved to the always-on Universal Rules (items 7, 8, and 9) because they bind before you open any of these trees: do not rely on Serena or Copilot Memory alone for a cross-harness convention, do not cite an operator preference as a repository rule, and do not assert an absence from a single probe.

## References

- `AGENTS.md`. Directs every harness to read `.claude/rules/*.md` by `paths` first; the Codex common denominator.
- `build/scripts/generate_rules.py`. Generates both instruction mirrors from `.claude/rules/`.
- `.claude/rules/generated-artifacts.md`. Regenerate-and-commit-in-the-same-change discipline.
- `.claude/rules/plugin-version-bump.md`. Why the manifests carry no version field.
- `.claude/rules/canonical-source-mirror.md`. Load-bearing "mirrors" claims must cite and quote the source.
