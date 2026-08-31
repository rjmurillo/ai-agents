---
paths:
  - "**"
priority: high
---

# Knowledge Persistence Rule

When you learn a durable fact, convention, or decision procedure that future sessions must honor, choose the persistence surface by who must obey it and across which harnesses. This repository runs under Claude, Codex, and Copilot; a convention living in one harness's memory is invisible to the other two.

## Placement contract

Six destinations, no overlap. Choose by what the content is, not by where it was learned.

| Destination | Content |
|-------------|---------|
| `.claude/rules/<name>.md` | A convention every contributor and harness must obey |
| `.claude/skills/<name>/SKILL.md` | A reusable procedure you run on demand |
| `.claude/agents/<name>.md` | A role contract needing persona, judgment, and isolated context |
| `.serena/memories/` (MCP-gated) or Copilot Memory (`store_memory`, per-user) | Evidence: what happened, what was measured, why. It cites; it never commands |
| Per-issue handoff | Unfinished state for this task only |
| Delete or merge | What another destination already carries |

Skill versus agent: the criteria are in `scripts/validation/check_agent_skill_discriminator.py` and the audit it cites. Do not restate them.

1. **Mandatory behavior MUST NOT depend on Serena retrieval** (MUST NOT 1 below, as placement). Serena is MCP-gated, Copilot Memory reaches neither Claude nor Codex, and a compacted session loses both. What must hold on every run is a rule, a skill, or an agent.
2. **Precedence**: a `.claude/` artifact outranks a memory on the same concept. The memory keeps evidence only and cites the artifact by path; a memory that contradicts it is the defect, whichever came first.
3. **Retention**: keep a thinned memory only while it holds evidence the artifact lacks (a measurement, an incident, a PR number). Delete it once it only paraphrases; a paraphrase drifts.
4. **Enforcement**: `scripts/validation/check_memory_placement.py`; exceptions via a `placement_exception:` frontmatter key or `[memory-placement: <rationale>]` in the PR body.

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

Write one when ALL of these hold, and skip it otherwise:

- Derived this session: observed behavior, a gotcha, a project-specific pattern, a decision rationale, a non-obvious codebase fact.
- Not already in a rule or a memory. Search Serena with 2-3 keywords first; if one covers it, augment that one, because a duplicate drifts once the original is updated.
- Not re-derivable by a `Grep` or `Read` in under a minute; reaching it took failed attempts, non-obvious traversal, or cross-file reasoning.
- Useful to a future session on the same area (5+ minutes saved), not ephemeral to this task.
- Not a guaranteed binding for every harness and contributor (see the placement contract above).

## MUST NOT

1. MUST NOT rely on Serena memory or Copilot Memory alone to persist a convention that other harnesses or contributors must obey. Those are retrieval complements, not the cross-harness binding.
2. MUST NOT hand-edit a generated mirror under `.github/instructions/` or `src/copilot-cli/instructions/`. Edit the canonical rule and regenerate.
3. MUST NOT cite an operator preference as a repository rule. Anything in a rule file or a Serena memory is repo-scoped, so it binds every contributor, while operator context such as `~/.copilot/copilot-instructions.md` or a personal `SOUL.md` binds one person on one machine. The two arrive in a session with identical authority and read identically once paraphrased, so the distinction cannot be recovered by feel. Before writing "the repository forbids X" or "per the standing prohibition on X", grep the rule tree for X and cite the file and item number, or drop the attribution and let the advice stand on its own reason. Measured: a memory asserted a repository prohibition on `rm -rf` that does not exist, and `.serena/memories/parallel/parallel-001-worktree-isolation.md` uses `rm -rf` as normal procedure, so the invented rule contradicted a committed memory in the same tree.
4. MUST NOT assert an absence from a single probe. This is the mirror of item 3 and is worse, because an absence is unfalsifiable by later reading: a cited presence claim gets checked the next time someone opens the file, while an absence claim has no such automatic trigger. Before writing that no script, validator, rule, or caller exists, search the whole repository from its root and cite the search, or narrow the claim to the scope actually searched. Measured: a memory asserted "No script regenerates these, and no validator checks them" after one probe of a guessed path, `scripts/memory/update_memory_index_tokens.py`. The regenerator and its pre-push ratchet both exist one directory up, lefthook runs both, and MUST-6 above names the regenerator by path, so the memory taught the anti-pattern a binding rule forbids (`78e808238`, corrected in `9cd7097f1`).

## References

- `AGENTS.md`. Directs every harness to read `.claude/rules/*.md` by `applyTo` first; the Codex common denominator.
- `build/scripts/generate_rules.py`. Generates both instruction mirrors from `.claude/rules/`.
- `.claude/rules/generated-artifacts.md`. Regenerate-and-commit-in-the-same-change discipline.
- `.claude/rules/plugin-version-bump.md`. Why the manifests carry no version field.
- `.claude/rules/canonical-source-mirror.md`. Load-bearing "mirrors" claims must cite and quote the source.
- `scripts/validation/check_memory_placement.py`. Placement gate for `.serena/memories/` (issue #5391).
