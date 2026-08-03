# Retrospective: fix/ci-infrastructure (2026-07-31)

## Session

Branch: fix/ci-infrastructure
PR: #4009
Issues: #3966, #3948, #3949, #3916, #3936, #3791, #3964

## What Shipped

- **#3966**: `run_mypy()` now refuses bare invocation (no paths); returns exit 2 instead of false green.
- **#3948/#3949**: `_run()` rewrites `Popen` in bytes mode with `_posix` guard; 300s dryrun budget; `_TIMEOUT_RC=124`.
- **#3916**: Added `_SKILL_REL_SCRIPT_PAT`, `find_skill_relative_scripts`, `_scan_skill_for_dangling`, `scan_dangling_skill_relative_scripts` to portability checker.
- **#3791**: Removed `import yaml` from `sync_adr_protocol.py`, replaced with stdlib regex.
- **#3936**: Removed inverted `detect_always_needed_patterns()` heuristic from context-optimizer.
- **#3964**: `test_workflow_job_permissions.py` ratchet gate for job permission inheritance.
- Fixed pre-push gate residues: SkillForge dangling refs (vendor-portability-exec markers), PR #4091 spurious type: ignore removal.

## What I Learned

1. Compression commits during rebase conflict with function additions: resolve by taking incoming for ALL conflict regions when HEAD has nothing in the region.
2. `_print_report` signature must be updated alongside the body when a new parameter is added; automatic conflict resolution leaves the signature behind.
3. The `--base-ref origin/main` type-ignore ratchet mode compares BASELINE FILES, not actual counts. Raising the baseline file is rejected even if the actual count went up on main without updating the baseline.
4. Markdown files with `# type:` inside string literals count against the type-ignore ratchet because the scan is raw text, not AST.
5. `markdown-autofix` runs on ALL staged files, including pre-existing lint errors. Touching any file forces fixing its pre-existing MD040/MD036 violations.

## What Did Not Work

- Rebasing `--onto origin/main` with a compression commit that references features not yet on main: conflict storm across 4 regions.
- Updating the type-ignore baseline to 56 to sync with main: `--base-ref origin/main` rejects any baseline increase regardless of actual count.

## Patterns to Carry Forward

- When fixing a false-positive detection: always add vendor-portability-exec marker immediately and run the detection test before committing.
- Before any push: run `uv run python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main` explicitly. The hook uses `--base-ref origin/main`, not the default mode.
