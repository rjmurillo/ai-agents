# Retrospective: Native Lefthook Migration

## Session Context

- **Date:** 2026-07-19
- **Branch:** `chore/lefthook-migration`
- **Outcome:** Replaced the custom Git hook engine with Lefthook 2.1.10.

## What Changed

- Moved scheduling, filtering, ordering, skips, stdin, and staging into
  `lefthook.yml`.
- Deleted `.githooks`, the temporary `scripts/hooks` relocation, the custom
  installer, compatibility wrappers, and SessionStart activation fallback.
- Added a narrow Python policy boundary for Git object and index operations
  that Lefthook cannot express.
- Replaced shell-shape tests with behavioral tests using real Git repositories
  and the real Lefthook binary.
- Updated active setup, contributor, workflow, security, and generated guidance.

## What Went Well

- The user rejected payload relocation early. That correction exposed the real
  goal: remove the custom engine, not rename it.
- Independent reviews found bypasses in globs, stdin sharing, alternate indexes,
  mutable security inputs, symlink handling, and generator staging.
- The final design uses native `{push_files}` instead of recreating a custom
  pushed-file manifest.
- The policy module reached 100 percent statement and branch coverage.

## What Could Improve

- The first implementation preserved too much custom machinery.
- Full repository validation came late and exposed prompt parity, test
  isolation, and type-narrowing gaps.
- The generic staged security scanner cannot read deleted files. The migration's
  immutable pushed-blob scanner avoids that failure mode.

## Learnings

1. Framework adoption succeeds only when the framework owns the behavior.
2. Shared hook stdin must have one sequential consumer group.
3. Security scans must read committed blobs, not mutable working-tree files.
4. Generated staging must follow successful generation in the same pipeline.
5. Native framework semantics are preferable to custom compatibility layers.
