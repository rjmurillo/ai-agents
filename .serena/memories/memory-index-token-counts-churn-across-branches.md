# The memory index token updater recounts every row, so branches collide on it

## The trap

Staging any `.serena/memories/**/*.md` file fires the `memory-token-update`
pre-commit job (`lefthook.yml:260`). That job runs
`scripts/update_memory_index_tokens.py`, which walks **every** link in
`memory-index.md` and recounts it, not just the file you staged. The next job,
`stage-memory-index` (`lefthook.yml:268`), auto-stages the rewrite into your
commit.

It recounts every row but rewrites only the rows whose count changed
(`update_line` replaces a row only `if new_count != old_count`). So the diff is
quiet when `main` is accurate and noisy when it is not, and you cannot predict
which from your own change. On a tree where every count is already correct the
script prints `Token counts in memory-index.md already current` and touches
nothing, which is why a clean run is not evidence that the hazard is absent.

So a one-memory change can silently carry corrections to rows you never
touched. Two branches that each add one memory will both rewrite the same
region of `memory-index.md` and conflict, even though neither author edited the
other's entry.

## Measured

2026-08-04, branch `docs/always-on-numbers-restale` against `origin/main`. Both
sides had 122 rows. Three counts differed, and only one was mine:

| entry | main | true | delta |
|---|---|---|---|
| `architecture/always-on-membership-lives-in-the-mirror.md` | 1283 | 1547 | +264 (mine) |
| `skills-git-index.md` | 287 | 324 | +37 |
| `skills-pr-review-index.md` | 1019 | 1054 | +35 |

`skills-git-index.md` is byte-identical across the merge base, `main`, and my
branch (blob `bb455ada316e4b10004bac3688a0cc01e835bc21`), so no content change
explains the delta. A forced recount and a direct `count_tokens()` call both
returned 324, so `main` was simply carrying a stale number that my unrelated
commit corrected.

## Why merge commits are the dangerous case

Both jobs carry `skip: - merge`. A merge commit gets no recount and no
auto-stage. When you resolve a `memory-index.md` conflict you are hand-picking
numbers with nothing behind you: `scripts/validation/memory_index.py` validates
that every entry resolves to a file, never that any count is current. It will
print `Result: PASSED` over a wrong number.

## Do this instead

Resolve the conflict by taking the union of both sides' rows, then let the tool
own the numbers:

```bash
# keep every row from both sides, then:
uv run --frozen python scripts/update_memory_index_tokens.py
uv run --frozen python scripts/validation/memory_index.py
git add .serena/memories/memory-index.md
grep -n "your-memory-file-name" .serena/memories/memory-index.md
```

`Token counts in memory-index.md already current` is the pass signal. If it
prints that, your hand-picked numbers happened to be right. If it rewrites the
file, they were not. Stage `memory-index.md` again after the updater, because
merge commits skip `stage-memory-index`. Never hand-edit a count and never
trust the validator's summary line to catch one.

## Why a fresh worktree recounts everything

Counts come from `tiktoken` `cl100k_base` via
`.claude/skills/memory/scripts/count_memory_tokens.py`. Results are cached in
`.serena/.token-cache.json`, keyed by the **absolute** file path and invalidated
by content hash. That file is gitignored (`.serena/.gitignore:5`), so every new
worktree starts cold and every path change misses the cache. The counts are
still deterministic for a given file's bytes; only the speed changes.

## Related

`.serena/memories/memory-index-validator-checks-one-direction-only.md` covers
the other half of this file's blind spot: the validator never walks the
filesystem, so an unindexed memory also passes.
