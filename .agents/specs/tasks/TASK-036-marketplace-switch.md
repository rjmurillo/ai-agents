---
type: task
id: TASK-036
title: Marketplace switch, claude-agents retired, project-toolkit repointed to src/claude (B6)
status: done
priority: P1
complexity: S
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
  - TASK-031
  - TASK-032
  - TASK-033
  - TASK-034
  - TASK-035
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-036: Marketplace switch, claude-agents retired, project-toolkit repointed to src/claude (B6)

## Objective

Drop the `claude-agents` entry from `.claude-plugin/marketplace.json`, repoint `project-toolkit`'s `source` from `./.claude` to `./src/claude`, delete `.claude/.claude-plugin/plugin.json`, and update `.github/plugin/marketplace.json`'s `project-toolkit` description to stop calling its source Claude canonical, since templates, not `.claude/`, are now canonical.

## In/Out of Scope

In scope: the two marketplace manifest edits, the one file deletion, and the description-text update. This is the customer-visible cut, last in the migration order per ADR-109 section 7, because a consumer who updates during the window between this task landing and any rollback keeps the new source until their next update, a one-way door for that window.

Out of scope: any change to `.claude-plugin/marketplace.json`'s or `.github/plugin/marketplace.json`'s `version` handling; ADR-092 (no manifest version) is unaffected, since this task edits `source` paths and a description string, not a version field. No further class migrates after this task; B1 through B5 must already be merged.

## Acceptance Criteria

- [x] `.claude-plugin/marketplace.json`'s plugins array names exactly one Claude-side plugin, `project-toolkit`, with `source: "./src/claude"`; no `claude-agents` entry remains.
- [x] `test -f .claude/.claude-plugin/plugin.json` exits nonzero after this task lands.
- [x] `test -f src/claude/.claude-plugin/plugin.json` exits 0, and its content is what was previously at `.claude/.claude-plugin/plugin.json` (the `project-toolkit` manifest, now sourced from the plugin tree that B1 through B5 render and binplace).
- [x] `.github/plugin/marketplace.json`'s `project-toolkit` description no longer reads "generated from Claude canonical sources"; its `source` path (`./src/copilot-cli`) is unchanged.
- [x] A fresh plugin install from the updated marketplace resolves `project-toolkit` at `./src/claude` with no missing file. The skill-loading smoke (`claude --plugin-dir src/claude plugin details project-toolkit`) passes: every skill name is listed (`RUN_CLI_E2E=1 uv run pytest tests/e2e/test_plugin_load_smoke.py -k claude -q`, 12 passed). The deeper completeness gap this task's own verification found, `src/claude/skills/<name>/` carrying only `SKILL.md` for 84 of 111 skills that also need `scripts/`, `references/`, or `tests/` under `.claude/skills/<name>/`, closed on `feat/adr-109-b3-skill-support-files` (merged `77a44751b`, #5794): `build/scripts/skill_support_mirror.py`'s `sync_claude_plugin_skill_support`, wired into `build_all.py`, mirrors those files into `src/claude/skills/<name>/` too. Verified after merging main: a direct file-by-file walk of every `.claude/skills/*/{scripts,references,tests}` file against its `src/claude/skills/` twin found zero missing; `tests/e2e/test_claude_skill_support_mirror_parity.py` (3 tests) and `build_all.py --check` (exit 0) both confirm. Example resolved: `src/claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py` now exists and is byte-identical to the `.claude/` copy.
- [x] The PR body states the rollback contract explicitly: reverting this task fixes future installs only, and any consumer who updated `project-toolkit` during the window between this task's merge and a revert keeps the `./src/claude`-sourced copy until their own next update.
- [x] `.agents/architecture/README.md` needs no change from this task alone (ADR-109's acceptance-time edits to ADR-052's status and the README's Accepted-to-Retired row move are governed by the ADR lifecycle process, not this implementation task).
- [x] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.claude-plugin/marketplace.json` | Modify | Remove `claude-agents` entry; repoint `project-toolkit`'s `source` to `./src/claude` |
| `.claude/.claude-plugin/plugin.json` | Delete | Superseded by `src/claude/.claude-plugin/plugin.json` |
| `src/claude/.claude-plugin/plugin.json` | Modify (or already present from earlier task setup) | Becomes the `project-toolkit` manifest |
| `.github/plugin/marketplace.json` | Modify | `project-toolkit` description text update; `source` unchanged |
| `.claude/rules/plugin-self-containment.md` | Modify | Plugin root table's `src/claude/` row description updates from "hand-maintained agent copy" to "compiled from templates, the sole Claude Code plugin root" |

## Implementation Notes

- This task assumes `src/claude/` is already a complete, self-contained plugin tree by the time it runs: agents (TASK-031, `src/claude/agents/`), rules (TASK-032, `src/claude/rules/`), the remaining skills (TASK-033, which also moves `skill_templates.compile_all`'s render target to `src/claude/skills/<name>/SKILL.md` for the first time and repoints the manifest's `skills` row's `plugin_tree` there), hooks and settings (TASK-034, which renders `src/claude/hooks/` and `src/claude/hooks.json` for the first time), and lib (TASK-035) must all be rendering into `src/claude/` before this switch, or the marketplace would point consumers at an incomplete tree.
- Single commit is likely sufficient given the file count (two manifest edits, one deletion, one rule-prose edit); do not force an artificial multi-commit split for a four-file change.
- Name the one-way-door risk in the PR description in plain terms: an existing installer who runs a plugin update between this merge and any later revert keeps the new source path until their next update after the revert, which is why this task is last.

## Testing Requirements

Positive: the marketplace manifest parses and resolves `project-toolkit` to `./src/claude` with every file a consumer would need present. Negative: `.claude/.claude-plugin/plugin.json` is confirmed absent, not merely unreferenced. Contract: whatever validates plugin manifests in CI today (`build_all.py --check` or a dedicated marketplace-schema check) passes on the edited files.

## Dependencies

TASK-031 through TASK-035 merged. This is the last task in ADR-109's migration order (section 7): "the marketplace switch last, because it is the customer-visible cut."
