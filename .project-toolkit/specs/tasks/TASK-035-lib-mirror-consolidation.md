---
type: task
id: TASK-035
title: Lib mirror absorbed into build_all.py, sync_plugin_lib.py retired (B5)
status: todo
priority: P1
complexity: M
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
  - TASK-031
  - TASK-032
  - TASK-033
  - TASK-034
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-035: Lib mirror absorbed into build_all.py, sync_plugin_lib.py retired (B5)

## Objective

Move `scripts/sync_plugin_lib.py`'s `SYNC_PAIRS` and `SYNC_FILE_PAIRS` copy logic (currently three whole-package syncs with relative-import rewriting into `.claude/lib/`, plus two individual file copies) inside `build/scripts/build_all.py`'s lib step, so `scripts/{hook_utilities,github_core,ai_review_common}/` copies directly into both `src/claude/lib/` and `src/copilot-cli/lib/` in the same run that renders every other class. Retire `scripts/sync_plugin_lib.py` as a standalone entry point.

## In/Out of Scope

In scope: absorbing the two-hop lib chain (`scripts/` to `.claude/lib/` to `src/copilot-cli/lib/`) into one step; the `lib` binplace manifest row; rewiring or retiring `scripts/ci/check_plugin_lib_mirrors.py`; rewriting `.claude/rules/generated-artifacts.md`'s "Generator order: sync before build" section, since the hazard it names no longer exists once one command performs both hops.

Out of scope: relocating `scripts/{hook_utilities,github_core,ai_review_common}/` under `templates/`; ADR-109 section 1 states this is the one class with a stated exception, because the packages carry absolute imports 39 lines inside themselves and 263 lines outside them depend on at their current path, and moving them would break every one with no compensating benefit since lib ships as compiled Python, not rendered prose.

## Acceptance Criteria

- [ ] `test -f scripts/sync_plugin_lib.py` exits nonzero after this task lands; `git log --oneline -- scripts/sync_plugin_lib.py | head -1` shows a deletion commit.
- [ ] `git diff --exit-code -- src/claude/lib src/copilot-cli/lib .claude/lib` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout in one invocation (no second script required).
- [ ] `uv run python build/scripts/build_all.py --check` exits 2 after a hand edit to any file under `.claude/lib/`, `src/claude/lib/`, or `src/copilot-cli/lib/`, and the hand edit is still present afterward.
- [ ] The three packages' relative-import rewrite (`IMPORT_CONVERSIONS`, unchanged regex table) still produces byte-identical `.claude/lib/<pkg>/` output to what `scripts/sync_plugin_lib.py` produced before this task, verified by diffing a pre-migration snapshot against the post-migration output for all three packages.
- [ ] `SYNC_FILE_PAIRS`'s two destinations land at their existing paths, `.claude/lib/bootstrap.py` and `.claude/skills/review/scripts/validate_review_marker.py` (verified 2026-09-11 against `scripts/sync_plugin_lib.py`'s `SYNC_FILE_PAIRS` list); the second path is outside every `lib` row's `.claude/lib` prefix and outside the `skills` row's per-skill-directory allowlist, so it gains its own manifest row (or an explicit second path on the `skills` row) so `assert_no_claude_writes` allowlists it. Verification: `uv run python build/scripts/build_all.py` writes `.claude/skills/review/scripts/validate_review_marker.py` with no REQ-003-010 violation reported for that path.
- [ ] `templates/platforms/binplace.yaml` gains the `lib` row(s), one per package or one aggregate row, whichever DESIGN-025's schema resolves to; `tests/build_scripts/test_binplace_manifest.py` passes with the new row(s).
- [ ] `grep -n "OWNED_PREFIXES" -A 8 build/scripts/build_all.py` lists `.claude/lib/` in the tuple; symlinking `.claude/lib/` and running `uv run python build/scripts/build_all.py --check` exits 2.
- [ ] `.claude/rules/generated-artifacts.md`'s "Generator order: sync before build" section, already rewritten at B1 (TASK-031) to describe the manifest-driven target architecture with a note that this specific hazard stayed open, has that note removed: the section now states the hazard no longer applies, since one command now performs both hops atomically.
- [ ] `scripts/ci/check_plugin_lib_mirrors.py` is either rewired to check the new single-step output or deleted, whichever the PR determines has no remaining caller; the decision and its reasoning are recorded in the PR body.
- [ ] `.github/CODEOWNERS` gains entries for `scripts/hook_utilities/` and `scripts/github_core/` and their `.claude/lib/` copies, matching the existing `scripts/ai_review_common/` entry already pinned.
- [ ] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `scripts/sync_plugin_lib.py` | Delete | Standalone entry point retired; its `SYNC_PAIRS`, `SYNC_FILE_PAIRS`, and `IMPORT_CONVERSIONS` logic moves, not its file |
| `build/scripts/build_all.py` (`_build_lib`, existing) | Modify | Absorbs the whole-package sync (with import rewrite) and the two individual file copies; now also writes `src/claude/lib/` alongside the existing `src/copilot-cli/lib/` target |
| `templates/platforms/binplace.yaml` | Modify | Add the `lib` row(s); add a row (or a second path on the `skills` row) covering `.claude/skills/review/scripts/validate_review_marker.py`, the `SYNC_FILE_PAIRS` destination outside every `lib` prefix |
| `build/scripts/build_all.py` (`OWNED_PREFIXES`) | Modify | Widen to include `.claude/lib/` |
| `scripts/ci/check_plugin_lib_mirrors.py` | Modify or Delete | Rewired to the new single-step output, or removed if `build_all.py --check` supersedes it |
| `.claude/rules/generated-artifacts.md` | Modify | "Generator order: sync before build" section rewritten; the hazard it names is eliminated by construction |
| `.github/CODEOWNERS` | Modify | Entries for `scripts/hook_utilities/`, `scripts/github_core/`, and their `.claude/lib/` copies |
| `.agents/governance/GENERATOR-FILES.md` | Modify | The `_build_lib` row's source description updates from `.claude/lib/` (a mirror-of-a-mirror) to `scripts/{hook_utilities,github_core,ai_review_common}/` directly |
| Any contributor tooling or documentation invoking `scripts/sync_plugin_lib.py` directly | Modify | Update to the equivalent `build_all.py` invocation |

## Implementation Notes

- This is a copy-logic relocation, not a rewrite: the `IMPORT_CONVERSIONS` regex table, the `SYNC_PAIRS` and `SYNC_FILE_PAIRS` lists, and their destinations move unchanged into `build_all.py`'s existing lib step. Verify byte-identity against the pre-migration output before removing the standalone script, not after.
- `build_all.py`'s comment referring to a "legitimate pre-build sync of `.claude/lib`" (cited by `.claude/rules/generated-artifacts.md` as evidence the sync is expected to run first) is now stale once the two steps are one step; update or remove that comment in the same commit.
- Atomic commits, five or fewer authored files each: `_build_lib` absorption plus deletion of `sync_plugin_lib.py` (2 files); manifest row (1 file); CI script rewire or deletion (1 file); rule rewrite plus CODEOWNERS (2 files); governance row (1 file).

## Testing Requirements

Positive: `src/claude/lib/`, `src/copilot-cli/lib/`, and `.claude/lib/` all byte-identical to what the absorbed logic produces from `scripts/{hook_utilities,github_core,ai_review_common}/`, in one `build_all.py` run. Negative: a hand edit to any of the three lib copies fails `--check`. Edge: the two individually-copied files (`bootstrap.py`, `validate_review_marker.py`) still land at their existing destinations unchanged. Contract: no test or script outside this task's changes still shells out to `scripts/sync_plugin_lib.py`; `grep -rln "sync_plugin_lib" --include="*.py" --include="*.md"` over the repository (excluding this task's own PR diff) returns nothing once merged.

## Dependencies

TASK-031 through TASK-034 merged. ADR-109 section 7 places lib after hooks and settings, before the marketplace switch.
