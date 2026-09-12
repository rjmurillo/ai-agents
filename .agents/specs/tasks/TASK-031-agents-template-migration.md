---
type: task
id: TASK-031
title: Agents composed from paired Claude/Copilot templates, src/claude/ layout move, binplace manifest introduced (B1)
status: todo
priority: P1
complexity: L
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-031: Agents composed from paired Claude/Copilot templates, src/claude/ layout move, binplace manifest introduced (B1)

## Objective

Introduce two NEW templates per agent, `templates/agents/<stem>.claude.md.tmpl` and `templates/agents/<stem>.copilot.md.tmpl`, for every one of the 31 agents, composed from shared partials under `templates/agents/partials/`, with any Claude-only section confined to the `.claude.md.tmpl` variant. The existing `templates/agents/<stem>.shared.md` is NOT replaced: it stays exactly as it is today, unchanged, as the sole source `src/vs-code-agents/` renders from (ADR-109 section 5, untouched seam). Render the Claude variant into `src/claude/agents/<stem>.md` for the first time (retiring `src/claude/`'s hand-maintained status) losslessly against today's content, repoint the Copilot mirror (`.github/agents/`, `src/copilot-cli/agents/`) to render from the Copilot variant losslessly against today's output, and introduce the binplace manifest under `templates/platforms/` that every later class's PR extends with its own row.

## In/Out of Scope

In scope: the two-variant template pair and shared-partials directory for all 31 agents, populated so the first render is byte-identical to today's `src/claude/<stem>.md` and today's `src/copilot-cli/agents/` output; `src/claude/security/references/` (3 files: `dependency-risk-scoring.md`, `powershell-security-checklist.md`, `threat-model-template.md`) moving alongside `security.md` to `src/claude/agents/security/`, part of the same layout move as the 31 agent files; `build/scripts/agent_templates.py` (discovery of template pairs, grammar and render reuse from `skill_template_grammar.py`, compile orchestration); `build/generate_agents.py` gaining the `src/claude/agents/` render target; `build/scripts/validate_install_parity.py`'s `src-claude` pattern and `detect_agent_drift.py`'s comparison pairs rewritten for the new path; `templates/platforms/binplace.yaml` created with two active rows, `agents` and `skills` (the `skills` row's targets delegate to `skill_templates.owned_targets`, `install_tree: .claude/skills`, `plugin_tree: null` until B3, so `assert_no_claude_writes`'s generalized allowlist keeps covering ADR-108's already-templated skills the moment this task retires the old skill-only call); `build_all.py`'s binplace step introduced and wired for the agents row (the skills row needs no binplace copy yet, since its `plugin_tree` is still `null`); `assert_no_claude_writes`'s `allowed_paths` argument generalized to read from the manifest; `OWNED_PREFIXES` widened to include `.claude/agents/`, the first `.claude/`-rooted entry that tuple carries, so the unreachable-owned-path symlink and containment check (issue #4632) covers the newly binplaced tree; `templates/platforms/copilot-cli.yaml`'s `agents` stanza's `sourceDir` repointed off `.claude/agents` to the agents template tree (a documentation-only edit: `build/generate_agents.py` never reads this field, so the repoint changes no rendered byte, only keeps the manifest from naming a path that is no longer the real source); `.claude/rules/generated-artifacts.md`'s "Generator order: sync before build" section rewritten to describe the manifest-driven target architecture, with an explicit note that the lib package's specific ordering hazard stays open until B5.

Out of scope: reconciling the 18 divergent agent pairs' content into genuinely shared partials (deferred to later, per-agent, owner-approved pull requests); rules, hooks, settings, lib, and the marketplace switch (TASK-032 through TASK-036); `templates/platforms/copilot-cli.yaml`'s `skills`, `rules`, and `lib` stanzas and its hooks `scriptSource`/`settingsSource` fields, which stay pointed at `.claude/` until their own class's migration task; `src/vs-code-agents/` and `AGENTS.md`/`claude-instructions.template.md` at the `src/claude/` root (excluded from the per-agent render today and untouched by this task).

## Acceptance Criteria

- [ ] `ls templates/agents/*.claude.md.tmpl templates/agents/*.copilot.md.tmpl | wc -l` returns 62 (31 pairs); `ls templates/agents/partials/*.mustache | wc -l` returns a nonzero count.
- [ ] `ls src/claude/agents/*.md | wc -l` returns 31; `ls src/claude/AGENTS.md src/claude/claude-instructions.template.md` still resolves both files at the plugin root, unmoved; `find src/claude/agents/security -type f | wc -l` returns 3, confirming `src/claude/security/references/` moved alongside `security.md`.
- [ ] Against a pre-task snapshot of `src/claude/*.md` and `src/copilot-cli/agents/`, the first `build_all.py` run under this task produces `src/claude/agents/<stem>.md` byte-identical to the snapshot's `src/claude/<stem>.md` for all 31 agents, and leaves `src/copilot-cli/agents/` byte-identical to its snapshot; `uv run pytest tests/build_scripts/test_agent_templates_lossless.py -v` passes.
- [ ] `git diff --exit-code -- src/claude src/copilot-cli/agents` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout.
- [ ] `uv run python build/scripts/build_all.py --check` exits 0 on a clean tree and exits 2 after a hand edit to any file under `src/claude/agents/`.
- [ ] `grep -n "src/claude/agents" build/scripts/validate_install_parity.py build/scripts/detect_agent_drift.py` shows both scripts matching the new path; neither script still matches the old flat `src/claude/<name>.md` pattern.
- [ ] `templates/platforms/binplace.yaml` exists, validated by a new `tests/build_scripts/test_binplace_manifest.py`, with exactly two active rows (`agents`, `skills`) and every `install_tree` resolving inside the repository root; the `skills` row's `install_tree` is `.claude/skills` and its `plugin_tree` is `null`.
- [ ] A pytest asserts the manifest-derived allowlist (`binplace_manifest.claude_allowlist(repo_root)`) is a strict superset of `skill_templates.owned_targets(repo_root)`, so retiring the old `skill_templates.owned_targets(repo_root)` call as `assert_no_claude_writes`'s sole `allowed_paths` source introduces no regression against ADR-108's already-templated skills.
- [ ] `grep -n "sourceDir" templates/platforms/copilot-cli.yaml` shows the `agents` stanza's value naming the agents template tree, not `.claude/agents`; the `skills`, `rules`, and `lib` stanzas and the hooks `scriptSource`/`settingsSource` fields are unchanged. `grep -n "sourceDir" build/generate_agents.py` returns zero matches both before and after this change, confirming the repoint is documentation bookkeeping, not a functional switch; `uv run pytest tests/build_scripts/test_agent_templates.py -k copilot` passes, asserting `src/copilot-cli/agents/<stem>.md` renders from `templates/agents/<stem>.copilot.md.tmpl`.
- [ ] `grep -n '"\.claude/agents/"' build/scripts/build_all.py` shows `.claude/agents/` added to `OWNED_PREFIXES`; hand-symlinking `.claude/agents/` and running `uv run python build/scripts/build_all.py --check` exits 2 (issue #4632's unreachable-owned-path check).
- [ ] `uv run pytest tests/build_scripts/test_agent_templates.py tests/build_scripts/test_binplace_manifest.py -v` passes, covering a two-variant-pair positive case, a missing-partial or malformed-template negative case, an incomplete-pair edge case (only one of the two variant templates present), and a symlinked `src/claude/agents/<name>/` negative case.
- [ ] `_Gate("Agent Template Drift", ...)` appears in `scripts/validation/pre_pr_sequence.py`'s registry and in `tests/validation/test_pre_pr_sequence_registry.py`'s `EXPECTED_ORDER`.
- [ ] `.github/CODEOWNERS` gains an entry for `/templates/platforms/` (the manifest defines the `.claude/` write allowlist, so it is owner-reviewed from this task on, per ADR-109 section 7).
- [ ] `.agents/governance/GENERATOR-FILES.md` gains a row for the agents compile step and drops `src/claude/<name>.md` from the hand-maintained sibling-copy table; `.claude/rules/claude-agents.md`'s description of `src/claude/` as hand-maintained is rewritten.
- [ ] `.claude/rules/generated-artifacts.md`'s "Generator order: sync before build" section describes the manifest-driven target architecture and states explicitly that the lib package's two-hop ordering hazard remains open until B5.
- [ ] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `templates/agents/<stem>.claude.md.tmpl`, `templates/agents/<stem>.copilot.md.tmpl` (62 files) | Create | Paired per-provider templates, initially populated to render losslessly against today's outputs |
| `templates/agents/partials/*.mustache` | Create | Shared text extracted where the two variants of a given agent already agree; a Claude-only section stays inline in its `.claude.md.tmpl`, not a partial |
| `build/scripts/agent_templates.py` | Create | `discover` (returns a `(claude_path, copilot_path)` pair per stem), `owned_targets`, `compile_all`, reusing `skill_template_grammar.check_grammar` and `render` |
| `build/generate_agents.py` | Modify | Add `src/claude/agents/` as a render target from the `.claude.md.tmpl` variant, alongside existing outputs rendered from the `.copilot.md.tmpl` variant |
| `build/scripts/validate_install_parity.py` | Modify | Rewrite the `src-claude` pattern for the new path; agents drop from the hand-maintained co-change set |
| `build/scripts/detect_agent_drift.py` | Modify | Rewrite comparison pairs for `src/claude/agents/<name>.md` |
| `templates/platforms/binplace.yaml` | Create | Binplace manifest, two active rows (`agents`, `skills`), per DESIGN-025 schema; the `skills` row delegates to `skill_templates.owned_targets` with `plugin_tree: null` until B3 |
| `templates/platforms/copilot-cli.yaml` | Modify | `agents` stanza's `sourceDir` repointed off `.claude/agents` (documentation-only; `generate_agents.py` does not read this field); every other stanza unchanged |
| `build/scripts/build_all.py` | Modify | Introduce `_binplace()`; generalize `assert_no_claude_writes`'s `allowed_paths` to read the manifest; widen `OWNED_PREFIXES` to include `.claude/agents/` |
| `build/scripts/binplace_manifest.py` | Create | Manifest load, validation (path containment), and allowlist derivation, per DESIGN-025 |
| `tests/build_scripts/test_agent_templates.py` | Create | Positive, negative, edge cases for the paired-template compile |
| `tests/build_scripts/test_agent_templates_lossless.py` | Create | Byte-identity fixture test against a pre-task snapshot of `src/claude/*.md` and `src/copilot-cli/agents/` |
| `tests/build_scripts/test_binplace_manifest.py` | Create | Manifest load and containment validation |
| `scripts/validation/checks_portability.py`, `pre_pr_sequence.py`, `pre_pr.py` | Modify | New `Agent Template Drift` gate wrapper, `_Gate` row, facade re-export |
| `tests/validation/test_pre_pr_sequence_registry.py` | Modify | `EXPECTED_ORDER` entry |
| `.agents/governance/GENERATOR-FILES.md`, `.claude/rules/claude-agents.md` | Modify | Rows and prose updated per DESIGN-025 |
| `.claude/rules/generated-artifacts.md` | Modify | "Generator order: sync before build" section rewritten to the manifest-driven target model; lib's residual hazard flagged open until B5 |
| `.github/CODEOWNERS` | Modify | `/templates/platforms/` entry |
| `src/claude/` (agent files) | Move | Flat files under `src/claude/*.md` (excluding `AGENTS.md`, `claude-instructions.template.md`, which stay in place) relocate to `src/claude/agents/*.md`; `src/claude/security/references/` (3 files) relocates to `src/claude/agents/security/references/` alongside `security.md` |
| `.claude/.claude-plugin/plugin.json`, `src/claude/.claude-plugin/plugin.json` | No change yet | The marketplace switch is B6; both manifests coexist unchanged through this task |

## Implementation Notes

- Populate each agent's initial `.claude.md.tmpl` from the pre-task `src/claude/<stem>.md` and each initial `.copilot.md.tmpl` from the pre-task `templates/agents/<stem>.shared.md`; do not attempt to merge the 18 divergent pairs into shared partials in this task. Extract a partial only where the two variants are already textually identical for that agent, so extraction never changes rendered output.
- Rewrite `validate_install_parity.py` and `detect_agent_drift.py`'s path patterns in the same commit as the render-target change, so no commit exists where the tool and the tree disagree.
- Repoint `copilot-cli.yaml`'s `agents.sourceDir` in the same commit that adds the agents row to `binplace.yaml`; this repoint is documentation bookkeeping, not a functional change, because `build/generate_agents.py` takes only `--templates-path` and `--output-root` and never reads the stanza's `sourceDir` field (verified 2026-09-11 by grep). The actual switch to rendering `src/copilot-cli/agents/` from `templates/agents/*.copilot.md.tmpl` happens because `generate_agents.py` itself changes what it globs under `--templates-path`, not because of this field. Leave every other stanza in that file untouched; each is repointed by its own migration task, and for those classes (`generate_rules.py`, `generate_skills.py`, the lib copy path) `sourceDir` is genuinely consumed, so repointing early would break their render.
- The binplace manifest ships with two rows active from this task: `agents` (a full `plugin_tree`/`install_tree` pair) and `skills` (`install_tree: .claude/skills`, `plugin_tree: null`, delegating to `skill_templates.owned_targets` until B3 gives skills its own plugin tree). Without the `skills` row, generalizing `assert_no_claude_writes`'s allowlist to read the manifest would silently stop covering ADR-108's already-templated skill writes; later tasks add their own new rows rather than this task staging placeholders for classes it does not touch.
- Widen `OWNED_PREFIXES` to add `.claude/agents/` in the same commit that introduces `_binplace()`, so the unreachable-owned-path check (issue #4632: a symlinked or unreadable path under `OWNED_PREFIXES` aborts `--check` with exit 2) covers the first `.claude/`-rooted binplace target. Later tasks each add their own class's prefix (`.claude/rules/`, `.claude/skills/` once B3 gives it a plugin tree, `.claude/hooks/`, `.claude/lib/`) when they land.
- Atomic commits, five or fewer authored files each: agent template pairs and partials, batched across several commits given 62-plus files (batch by a natural grouping, e.g. ten agents per commit); compile module (1 file); compile-target change plus drift-pattern rewrites (3 files); manifest plus binplace step plus its module plus the `copilot-cli.yaml` sourceDir edit (4 files); tests (3 files); pre_pr wiring plus registry test (4 files); governance, generated-artifacts rewrite, and CODEOWNERS (4 files).
- This task lands the migration order's first PR; ADR-109 section 7 states agents go first because D2 measures the largest unguarded drift.

## Testing Requirements

Positive: both variants of a fixture pair render byte-identical to expected output; the 31-agent losslessness test passes against the pre-task snapshot. Negative: a missing partial or disallowed tag exits 2, target untouched; a Claude-only line leaking into the Copilot variant fails the losslessness test against the pre-task Copilot snapshot. Edge: a stem with only one of its two variant templates present is a configuration error, not a partial compile. Contract: `build_all.py --check` on a drifted `src/claude/agents/` file exits 2 and writes nothing.

## Dependencies

None. Lands first, per ADR-109 section 7.
