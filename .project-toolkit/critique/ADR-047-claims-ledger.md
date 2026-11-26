# ADR-047 Claims Ledger: 2026-11-24 amendment

Scope: the amendment "Skill scripts that load the shared parser prefer their own lib".
Measured in worktree `fix/frontmatter-followups` at base `84c395f822` (2026-11-24).

| # | Claim | Kind | Command | Result |
|---|-------|------|---------|--------|
| 1 | 18 authored scripts use the shape | count | `git grep -l '_LIB_DIR / "hook_utilities" / "frontmatter_block.py"' -- src/claude/skills .claude/skills \| wc -l` | VERIFIED: 18 |
| 2 | Each sits at `<plugin>/skills/<name>/scripts/` | path | same list, `awk -F/ '{print NF}'` | VERIFIED: 2 paths of 5 parts (`.claude/...`), 16 of 6 parts (`src/claude/...`); `parents[3]` is the plugin root in both |
| 3 | codex, cursor, muse, hermes carry no `.claude-plugin/plugin.json` | absence | `ls src/<tree>/.claude-plugin/plugin.json` for each tree | VERIFIED: present in `src/claude`, `src/copilot-cli`; absent in `src/codex`, `src/cursor`, `src/muse`, both `src/hermes/*` packs |
| 4 | Every plugin lib tree holds the parser | count | `ls src/*/lib/hook_utilities/frontmatter_block.py src/hermes/*/lib/hook_utilities/frontmatter_block.py` | VERIFIED: 7 files |
| 5 | ADR-121's locator keys on `lib/ptk_run.py` | quote | `grep -n 'ptk_run.py' .project-toolkit/architecture/ADR-121-one-resolver-for-plugin-root-commands.md` | VERIFIED: lines 103, 109, 112 |
| 6 | The test covers stale root, missing parser, fallback, 3.10 floor | behavior | `grep -n '^def test_' tests/test_frontmatter_bootstrap_foreign_root.py` | VERIFIED: lines 100, 108, 120, 132, 142, 167 |
| 7 | `test_plugin_path_resolution.py` checks for `CLAUDE_PLUGIN_ROOT` | quote | `grep -n CLAUDE_PLUGIN_ROOT tests/test_plugin_path_resolution.py` | VERIFIED: line 4 states the rule; each of the 18 scripts reads the variable |
| 8 | An older parser without `fence_end` could load env-first | behavior | agent-safety axis F1, PR #7531 review at `2ea364726` | VERIFIED: recorded finding; fixed in `594e49916` |
| 9 | Three review axes flagged env-first | quote | PR #7531 review outputs (architect, security, agent-safety) | VERIFIED |
| 10 | Neither lib holding the parser fails loudly | behavior | correctness axis at `881290c0b`: `RuntimeError` when the lib dir is missing, `ImportError` otherwise | VERIFIED |
| 11 | The build mirrors the shape into every plugin tree that ships those skills | count | `git grep -l '_LIB_DIR / "hook_utilities" / "frontmatter_block.py"' -- src/hermes \| wc -l` | VERIFIED: 13 hermes copies; the packs carry a subset of skills. Reworded from "every plugin tree" after the refuting seat |
| 12 | PR #7531 changed no hook | absence | `git diff --stat 84c395f822^1 84c395f822 -- src/claude/hooks .claude/hooks templates/hooks` | VERIFIED: empty |
| 13 | Standard boilerplate exits 2 only for a missing lib directory | behavior | ADR-047 lines 95-100 | VERIFIED: reworded after the refuting seat |
| 14 | The 3.10 case runs only when an interpreter exists | behavior | `tests/test_push_pr_interpreter_floor.py` `requires_python310` | VERIFIED: reworded after the refuting seat |
| 15 | Both tests pass | behavior | `uv run --frozen pytest -q tests/test_plugin_path_resolution.py tests/test_frontmatter_bootstrap_foreign_root.py` | VERIFIED: 87 passed at the merged tree, 2026-11-24 |
| 16 | 14 other skill scripts carry their own bootstraps | count | `git grep -l 'parents\[3\]' HEAD -- 'src/claude/skills/*.py' '.claude/skills/*.py'`, keeping files that contain `CLAUDE_PLUGIN_ROOT` or `COPILOT_PLUGIN_ROOT` and do not contain `frontmatter_block` | VERIFIED: 14 files at HEAD and 15 at origin/main `148d7ad72`, 2026-11-25, counted by a Python loop over `git show` blobs. The net change is `council.py` and `sol_loop.py` out, `scan_principles.py` in |
| 17 | The environment root is COPILOT first, then CLAUDE | behavior | `src/claude/skills/adr-review/scripts/detect_adr_changes.py:37` | VERIFIED |
| 18 | The bootstrap test finds copies by parser import and the `parents[3]` line | behavior | `tests/test_frontmatter_bootstrap_foreign_root.py` `_PROBES`, `_BOOTSTRAP` | VERIFIED |
