# Serena Memory Subdirectory Convention

## Summary

As of 2026-02-14, Serena memories are organized into topic subdirectories under `.serena/memories/`.

## Key Behavior

- `list_memories` returns ONLY top-level files (indexes)
- `read_memory("subdir/name")` reads files from subdirectories
- `write_memory("subdir/name", content)` writes to subdirectories

## Convention

- **Index files** (`*-index.md`, `README.md`, `usage-mandatory.md`): top level
- **Atomic memories**: in topic subdirectory matching their domain
- **Index references**: use `subdir/memory-name` format

## Token Impact

Reduced `list_memories` output from 829 entries (~5,000 tokens) to 45 entries (~300 tokens). Savings: ~4,700 tokens per session.

## Known breakage: the migration outran the tools that read the corpus

This convention was applied to the data on 2026-02-14, but not every tool that
enumerates the corpus was updated with it. `list_memories` was handled, and this
memory recorded that. `search_memory.py` was not, and nothing failed loudly.

`.claude/skills/memory/scripts/search_memory.py` enumerated with a
non-recursive `glob("*.md")`, so it only ever saw top-level files. After the
migration moved 829 memories into subdirectories, the search reached 123 of 974
files, or 12.6% of the corpus, and missed all 851 nested ones. It returned no
error and no warning. It returned
a confident empty result.

The practical consequence is worse than a slow search. The house rule "search
the corpus before writing a memory" silently could not work for any nested
memory, which is the overwhelming majority of them. Following the rule and
getting nothing back was indistinguishable from the topic being genuinely
uncovered, so the rule produced duplicates instead of preventing them.

Fixed in issue #4655 / PR #4656 by switching to `rglob` and deriving the
returned `Name` from the path relative to the memory root, so a nested hit
returns `ci/foo` and is directly usable with `read_memory("subdir/name")` as
documented above. The same enumeration bug also made the reported
`MemoryCount` read 123 instead of 974, and hit the ADR-037 library path in
`memory_core/memory_router.py` identically, so both were fixed together.

That PR fixes the search path only. A wider sweep found roughly eleven other
non-recursive walkers over `.serena/memories` (health, staleness, freshness,
and conversion scripts). Each needs the same enumerate-then-verify treatment
before its output can be trusted. Do not assume a memory-corpus statistic is
corpus-wide until you have read how that script enumerates.

The transferable lesson: when a data layout changes, the loud consumer gets
fixed because it breaks visibly, and the quiet consumer keeps returning
plausible wrong answers. Enumerate the readers of a corpus before you
reorganize it, and prefer a check that fails loudly over one that returns an
empty list.

Not every non-recursive reader is a defect. The pre-push memory size gate reads
staged paths from `git diff --cached -- .serena/memories` rather than walking a
directory, so it covers nested files correctly and needs no change. Check how a
consumer enumerates before assuming it shares this bug.

## The index token counts are tiktoken, and are machine-maintained

The `(NNN)` after each entry in `memory-index.md` is a real `tiktoken`
`cl100k_base` count of the file, not `chars / 4` and not a word multiple.
Verified against two existing entries, which reproduce exactly:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
len(enc.encode(open(path).read()))
```

Do not compute or type that number yourself. `.claude/rules/knowledge-persistence.md`
MUST-5 says to write `(0)` as the placeholder; the `memory-token-update`
pre-commit job rewrites it to the real count. That job carries
`skip: [merge, "test $SKIP_AUTOFIX = 1"]`, so a memory edited inside a merge
commit keeps a stale count and the pre-push `memory-index-token-ratchet` fails
and names it. MUST-6 says to repair that by running
`uv run --frozen python scripts/update_memory_index_tokens.py`, "not by editing
the number by hand". Note the path: `scripts/`, not `scripts/memory/`.

Knowing the encoding is still useful for reading the index, and for
understanding why a guess drifts. It is not a license to hand-edit: on pristine
`main` before the ratchet existed, `skills-git-index` merged with 287 against an
actual 324, a 13% undercount (Issue #4441).

The `(NN%)` in an H1 is unrelated. It is a confidence marker, not a size or
completeness figure: a 13,847-char memory carries `(95%)`. Do not recompute it
from the file.

## Related

- README.md (top-level) for full directory structure documentation
- Migration script: `scripts/restructure_memories.py`
