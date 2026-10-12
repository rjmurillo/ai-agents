# The /tmp inode cap, not disk bytes, stopped every tool call during parallel pushes

## What happened

On 2026-10-11, parallel agent pre-push runs filled the `/tmp` tmpfs inode table. `df -i /tmp` showed 1,048,560 of 1,048,576 inodes used while byte usage was 18 percent. The cap on this host was 1,048,576.

Contributors to the count: pytest base temp trees at about 560,000 files, plus leaked count-ratchet scratch directories from killed pushes (issue #6292).

## Why it stopped everything

Every tool call failed with ENOSPC ("No space left on device"). The agent harness writes each call's output under `/tmp`, so a full inode table breaks the harness itself, not only the push.

## What helps and what does not

- Run about 3 parallel pushes at most.
- Set `TMPDIR=$HOME/.cache/ai-agents-tmp/<branch>` before pytest, `pre_pr.py`, and push. This moves pytest and ratchet scratch to the home disk.
- `TMPDIR` does not move the harness output directory. Throttling parallel pushes is the only guard for that part.
- Check with `df -i /tmp`, not `df -h`. The byte view looks healthy.

## Sources

- Issue #6292 (observed counts, leaked `/tmp/merge-tree-ratchet-*` directories).
- Ship contract step 3a for the sweep.
