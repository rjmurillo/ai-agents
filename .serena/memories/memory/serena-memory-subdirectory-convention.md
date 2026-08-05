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
migration moved 829 memories into subdirectories, the search reached 123 of 968
files, or 12.7% of the corpus. It returned no error and no warning. It returned
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
`MemoryCount` read 123 instead of 968.

The transferable lesson: when a data layout changes, the loud consumer gets
fixed because it breaks visibly, and the quiet consumer keeps returning
plausible wrong answers. Enumerate the readers of a corpus before you
reorganize it, and prefer a check that fails loudly over one that returns an
empty list.

Not every non-recursive reader is a defect. The pre-push memory size gate reads
staged paths from `git diff --cached -- .serena/memories` rather than walking a
directory, so it covers nested files correctly and needs no change. Check how a
consumer enumerates before assuming it shares this bug.

## The index token counts are tiktoken, not an estimate

The `(NNN)` after each entry in `memory-index.md` is a real `tiktoken`
`cl100k_base` count of the file, not `chars / 4` and not a word multiple.
Verified against two existing entries, which reproduce exactly:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
len(enc.encode(open(path).read()))
```

No script regenerates these, and no validator checks them, so a hand-written
guess persists silently. Compute the real value when you add or resize a memory.

The `(NN%)` in an H1 is unrelated. It is a confidence marker, not a size or
completeness figure: a 13,847-char memory carries `(95%)`. Do not recompute it
from the file.

## Related

- README.md (top-level) for full directory structure documentation
- Migration script: `scripts/restructure_memories.py`
