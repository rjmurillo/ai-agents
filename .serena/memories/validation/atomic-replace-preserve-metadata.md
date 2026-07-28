# Skill: Preserve Destination Metadata During Atomic Replacement

## Statement

When replacing an existing file through a sibling temporary file, copy required destination metadata before `os.replace()`.

## Trigger

Any fix that changes an in-place write to temporary-file plus atomic replacement.

## Action

1. Write the complete payload to a sibling temporary file.
2. Preserve required metadata, including POSIX mode bits, from the destination.
3. Replace the destination only after the temporary write and close succeed.
4. Test content safety on write and replace failures, temporary cleanup, and metadata preservation.

## Evidence

Issue #3357 changed the causal-graph merge driver (`scripts/validation/merge_causal_graph.py`) from direct `Path.write_text()` to atomic replacement. An empirical probe found the first implementation changed mode `0644` to `0600`; copying `stat.S_IMODE(path.stat().st_mode)` before replacement fixed it. That driver was deleted by ADR-089, so the code is reachable only in git history. The rule stands for any atomic replacement.

## Failure Mode

Content-only tests can approve an atomic replacement that silently changes permissions or other required metadata.

## Atomicity

**Score**: 97%

## Category

validation
