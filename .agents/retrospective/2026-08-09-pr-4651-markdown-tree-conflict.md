# Retrospective: PR #4651 merge-tree repair

## Session 2026-08-08

### Learnings captured

- Merge-tree ratchets can fail on a small shared hunk, even when the functional change is unrelated.
- Moving or removing the shared hunk is the fastest way to restore an auto-merge path.
- Required push gates may still require explicit retrospective evidence after tests and ratchets pass.
