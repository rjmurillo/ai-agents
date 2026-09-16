---
applyTo: .github/instructions/**,src/copilot-cli/instructions/**,templates/rules/**
---

# Knowledge Persistence Rule

This rule covers the mechanics of writing to a persistence surface: rule files, the mirrors generated from them, and Serena memories. It fires when you edit one of those trees.

Choosing which surface a fact belongs on binds earlier, before you know which tree you will open. The always-on Universal Rules give the three-tier summary under "Choosing a persistence surface"; the five-class Placement contract below is the full decision procedure it points to.

## MUST

1. **Canonical rule lives in `templates/rules/`**. A convention that must bind across Claude, Codex, and Copilot MUST be written to `templates/rules/<name>.md`, not only to Serena memory or Copilot Memory (ADR-109 B2: `templates/rules/` is the edit location for every rule `rule_templates.py` compiles, `testing.md` included; its GitHub Actions example writes the literal `${{ a && b }}` using the backslash-before-tag literal-brace escape, see the generator table in governance). `AGENTS.md` directs every harness to read `.claude/rules/*.md` first, so Claude (reads the compiled, binplaced tree directly) and Codex (reads `AGENTS.md`) both resolve to it, and Copilot reads the generated mirror.
2. **Regenerate the mirrors in the same change**. Adding or editing a `templates/rules/<name>.md` file MUST regenerate `src/claude/rules/<name>.md`, `.claude/rules/<name>.md`, `.github/instructions/<name>.instructions.md`, and `src/copilot-cli/instructions/<name>.instructions.md`, committed in the same change. Run the one command `.claude/rules/generated-artifacts.md` documents:

   ```bash
   uv run python build/scripts/build_all.py
   ```

   This command compiles the template, binplaces it, and regenerates both instruction mirrors; a stale mirror is torn state (see `.claude/rules/generated-artifacts.md`).
3. **Leave the plugin manifests alone**. `.claude/` and `src/copilot-cli/` ship in the project-toolkit plugin, but the manifests carry no `version` field: Claude Code resolves freshness from the commit SHA instead, so a rule change needs no manifest edit. Adding a `version` back fails `build/scripts/validate_plugin_version_bump.py` (see `.claude/rules/plugin-version-bump.md` and ADR-092).
4. **Scope by `paths:`**. Set `paths:` to the narrowest glob that fires where the convention applies (`tests/**`, `**/*.ps1`). A universally-binding convention sets `paths: ["**"]`.
5. **Index a new Serena memory by hand**. A memory under `.serena/memories/` MUST get a keyword line in `memory-index.md` in the same change, or keyword retrieval cannot reach it. `memory_index.py --ci` checks only that index rows resolve to files, never the reverse, so nothing catches the omission. Write `(0)` as the token placeholder; the `memory-token-update` pre-commit job rewrites it to the real count.
6. **Repair token counts by hand when the autofix is skipped**. `memory-token-update` carries `skip: [merge, "test $SKIP_AUTOFIX = 1"]`, so a memory edited inside a merge commit, or committed with `SKIP_AUTOFIX=1`, keeps a stale count. Pre-push `memory-index-token-ratchet` then fails and names every stale entry. Fix it by running `uv run --frozen python scripts/update_memory_index_tokens.py`, not by editing the number by hand. Measured on pristine `main` before the ratchet existed: `skills-git-index` recorded 287 against an actual 324, a 13% undercount that merged (Issue #4441).
7. **Place by activation semantics**. A new file under `.serena/memories/` MUST hold evidence, not policy; see Placement contract. Normative or procedural content goes to the rule, skill, or agent that owns the behavior.

## SHOULD

1. **Prefer an existing rule file**. Before adding a new `.claude/rules/*.md`, SHOULD add the item to the closest existing rule (a testing convention to `.claude/rules/testing.md`, a security convention to `.claude/rules/security.md`). Create a new file only when no existing rule owns the concern.
2. **Cite the incident**. SHOULD name the failure, PR, or review that motivated the convention, so the next reader can weigh it (mirrors `.claude/rules/governance.md` "Evidence required").

## Placement contract

This section is the authoritative taxonomy for where repository knowledge lives (issue #5391). Placement follows activation semantics, not directory names or convenience. A required behavior MUST NOT depend on Serena retrieval to activate, because Serena is MCP-gated and not loaded on every harness.

| Class | Holds | Activates when | Lives at |
|---|---|---|---|
| Rule | Cross-cutting normative invariant: must, never, always, required recovery, scope discipline, safety or quality gate | Its `paths:` scope matches the file under edit | `templates/rules/<name>.md` (path-scoped by `paths:`; always-on only when it binds every task) |
| Skill | Repeatable task, workflow, procedure, or tool-using capability, including its own workflow-specific normative text | Invoked by task intent | `.claude/skills/<name>/SKILL.md` plus the skill's own script and reference subdirectories |
| Agent | Role-specific specialization: authority, responsibilities, entry criteria, outputs, handoff contract for a distinct persona | A session takes on that persona | the agent's template trio under `templates/` (`<name>.claude.md.tmpl`, `.copilot.md.tmpl`, `.shared.md`; see `templates/AGENTS.md`) |
| Memory | Empirical observation, measurement, incident record, learned lesson, or rationale whose applicability still needs judgment | A future session searches Serena for the topic | `.serena/memories/<topic>/<name>.md` |
| Delete/merge | Duplicate explanatory text, obsolete index, stale copy, content fully represented elsewhere with no evidentiary value left | Never; it should not exist | Nowhere |

### Where a new item goes

| Question | Answer |
|---|---|
| New learned observation? | Memory. |
| New mandatory agent behavior? | If it binds one skill's workflow, put it in that skill. If it binds every task on matching paths, a path-scoped rule. Always-on only for cross-cutting content (epic #5456 decision, 2026-09-11). |
| Repeatable workflow? | Skill. |
| Role-specific behavior? | Agent. |
| When to keep a memory after its content moves into an artifact? | When it still carries evidence, a measurement, or rationale the artifact does not. |
| When to delete a memory? | When the artifact fully represents it and it carries no evidentiary value. |
| Which wins when a memory and a rule, skill, or agent disagree? | The rule, skill, or agent. The memory is evidence, not policy. |

### Authoritative source on overlap

When a memory and a rule, skill, or agent describe the same behavior, the rule, skill, or agent is authoritative. The memory is evidence, not policy: keep only the observation, measurement, incident, or rationale, and link it to the artifact that owns the behavior. Migration under #5392 and #5393 applies this rule; it decides no new taxonomy.

### Placement check for new memories

The `memory-placement` pre-commit job runs the memory placement check (`check_memory_placement.py` under the validation-scripts tree; the directory prefix is omitted because this rule ships in the plugin instruction mirrors, where an upstream-only path would dangle). It flags a newly added memory that reads as normative or procedural: a high density of MUST, MUST NOT, SHALL, must not, never, always, required; a heading named Constraints, Guardrails, Workflow, Procedure, Protocol, Responsibilities, Entry Criteria, or Acceptance Criteria; a long numbered procedure; or a role contract (two or more of Role, Authority, Entry Criteria, Outputs, Handoff, Responsibilities as headings). An existing memory only warns; a newly added one that reads as policy fails.

Suppress a false positive with an HTML comment anywhere in the file, exact form:

```text
<!-- placement: evidence; reason: <why this is evidence, not policy> -->
```

A suppression with an empty or missing reason is rejected.

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
4. **Which surface?** See Placement contract above for the full taxonomy.
   - Binds every task on matching paths -> rule (`templates/rules/<name>.md` + mirrors)
   - Repeatable procedure by task intent -> skill (`.claude/skills/<name>/SKILL.md`)
   - Role contract -> agent (the `<name>.claude.md.tmpl` trio under `templates/`)
   - Evidence or rationale -> memory (`.serena/memories/<topic>/<name>.md`)
   - Already fully represented elsewhere -> delete or merge

## MUST NOT

1. MUST NOT hand-edit a generated mirror under `.github/instructions/` or `src/copilot-cli/instructions/`. Edit the canonical rule and regenerate.

Three further MUST NOT items moved to the always-on Universal Rules (items 7, 8, and 9) because they bind before you open any of these trees: do not rely on Serena or Copilot Memory alone for a cross-harness convention, do not cite an operator preference as a repository rule, and do not assert an absence from a single probe.

## References

- `AGENTS.md`. Directs every harness to read `.claude/rules/*.md` by `paths` first; the Codex common denominator.
- `build/scripts/generate_rules.py`. Generates both instruction mirrors from `.claude/rules/`.
- `.claude/rules/generated-artifacts.md`. Regenerate-and-commit-in-the-same-change discipline.
- `.claude/rules/plugin-version-bump.md`. Why the manifests carry no version field.
- `.claude/rules/canonical-source-mirror.md`. Load-bearing "mirrors" claims must cite and quote the source.
