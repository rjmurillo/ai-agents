# Independent QA Report: Native Lefthook Migration

**Branch:** `chore/lefthook-migration`
**Date:** 2026-07-19
**Result:** PASS

## Acceptance

The migration removes the custom Git hook engine. `lefthook.yml` now owns hook
events, named jobs, file filters, ordering, skips, stdin, and staging. No
`.githooks`, `scripts/hooks`, custom installer, compatibility wrapper, or
SessionStart activation fallback remains.

The Python policy boundary handles only behavior Lefthook cannot express:
staged Git blobs, alternate indexes, pushed refs, immutable commit scans,
generated allowlist staging, and memory policies.

## Evidence

| Check | Result |
|-------|--------|
| Full repository tests | 14,093 passed, 22 skipped, 45 xfailed |
| Targeted migration suite | 439 passed |
| Lefthook integration suite | 171 passed |
| Policy coverage | 100 percent statements and branches |
| Pre-PR validation | 30 passed, 0 failed, 4 skipped |
| Generated artifact drift | Pass |
| Changed Python Ruff and per-file mypy | Pass |
| Markdown, YAML, actionlint, workflow local tests | Pass |
| Changed-file Semgrep | 28 files, 0 findings |
| Security suppression policy | Pass |
| Lefthook 2.1.10 validation | Pass |

## Behavioral Coverage

The integration suite creates scratch Git repositories and invokes the real
Lefthook binary. It covers installation, linked worktrees, nested globs,
alternate indexes, commit-message rejection, stdin replay, protected ref
deletion, immutable pushed-commit scans, native `{push_files}`, generator
failure ordering, skip controls, and generated staging.

## Notes

The generic staged vulnerability scanner reported deleted files as read errors
and flagged unchanged bootstrap text. The migration's changed-file Semgrep run
completed with zero findings. Its pushed-ref security path reads immutable Git
blobs and ignores deleted paths by design.

## Verdict

PASS. The repository now uses the framework as the hook system instead of
relocating the former shell engine behind a Lefthook wrapper.
