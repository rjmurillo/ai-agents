---
name: memory-consolidate
version: 0.1.0
description: Reflective consolidation pass over Serena memory files. Separates
  durable context (preferences, working style, key relationships, recurring
  workflows) from dated context (projects, deadlines, one-off tasks), merges
  duplicate topic files onto the richer path, converts relative dates to
  absolute ones, and tidies memory-index.md so a future session orients fast
  without re-asking. Use when you say `consolidate memory`, `consolidate
  Serena memory`, `merge memory files`, or `tidy the memory index`. Do NOT use
  for Forgetful-store curation (use curating-memories) or health, token, or
  size checks (use memory-maintenance).
license: MIT
---

# Memory Consolidate

This is a periodic pass, not a per-session check. Run it so a future session
can orient on who the user works with, what they are focused on now, and how
they like to work, by reading a small, current set of memories instead of
re-deriving that context or re-asking the user.

This is separate from `memory-maintenance`, which measures store health, and
`curating-memories`, which curates the Forgetful store. It owns the reflective
Serena file pass because neither sibling merges duplicate topic memories or
separates durable user context from dated work.

## Triggers

Use this skill when the user says:

- `consolidate memory` for a full durable-versus-dated review and index tidy
- `consolidate Serena memory` for pruning stale or thin Serena memory files
- `merge memory files` for combining overlapping topic files
- `tidy the memory index` for trimming `memory-index.md` alone

## Tool Order

Each tier is tried before falling back to the next one:

1. **Memory skills first.** If available, use memory search to rank and list
   topic files by keyword.
2. **Serena second.** Use Serena's list-memories and read-memory capabilities
   only after confirming Serena is active on the repository being
   consolidated. If the active project is unknown or different, use direct
   directory access instead. Phase 1 below states what list-memories does and
   does not enumerate.
3. **Direct directory access third.** Only when the above are unavailable,
   read `.serena/memories/` and its topic subdirectories directly. The one
   exception is Phase 1's bounded stale-index audit, which always compares
   relevant subdirectory filenames with their index entries, even when a
   higher discovery tier succeeded.

These three tiers govern discovery only: how you find out which memory files
exist.

## Process

### Phase 1: Take Stock

1. List the top-level memory files (memory search, Serena's list-memories
   capability, or direct `ls .serena/memories` per the Tool Order above) and
   read `memory-index.md` in full. Serena list-memories enumerates top-level
   files only: atomic topic memories in subdirectories are hidden from it.
   A plain `ls` at this step has the same indexes-only limitation, so read
   each relevant `*-index.md` next and use the paths it names to reach and
   skim the atomic memories themselves
   (Serena's read-memory capability or direct file reads under
   `.serena/memories/topic/`). Fall back to listing a subdirectory's contents
   directly only when its index looks stale or incomplete against what the
   directory actually holds. Then perform one bounded stale-index audit
   regardless of discovery tier: compare each relevant topic directory's
   Markdown filenames with its `*-index.md` entries. Add unindexed files to
   the Phase 1 inventory and record dangling index entries as errors.
2. Skim each file for three signals: **overlap**
   (two or more files cover the same person, project, or preference),
   **staleness** (a one-off task that passed its date), and **thinness** (a
   file that does not earn its own retrieval cost). Compare it with
   neighboring topic memories and split only when it mixes distinct concepts.

### Phase 2: Consolidate

Separate what you found in Phase 1 into two buckets:

- **Durable**: preferences, working style, key relationships, recurring
  workflows. Keep these, and sharpen them: cut hedging and resolved detail,
  while preserving the recorded meaning.
- **Dated**: projects, deadlines, one-off tasks. When a dated memory has
  passed or completed, delete it after folding any lasting takeaway into the
  relevant durable memory. Git is the audit trail and recovery path. Do not
  preserve a dead file just to explain the deletion.

Before editing, require no unrelated changes under `.serena/memories/`. This
keeps the consolidation diff reviewable and makes any mistaken deletion
recoverable from git without another agentic pass. If the memory tree is not
tracked by git, do not delete files; report the prerequisite instead. Check
both conditions before the first edit:

```bash
git status --short -- .serena/memories
git ls-files --error-unmatch .serena/memories/memory-index.md
```

- **Merge only genuine duplicates.** Two files are merge candidates only
  when they would both answer the same lookup query about the same person,
  project, or preference, and one is clearly the poorer, older version.
  Sharing a domain, sitting in the same index section, or being topically
  adjacent is not enough: never combine two distinct atomic concepts (for
  example, a contact's communication preference and an unrelated project's
  status) just because they overlap in some other way.
  When you find a genuine duplicate: identify the richer path (more current,
  more cross-linked, more concrete content), fold every unique fact from the
  poorer file into it, validate the survivor, delete the poorer file, and
  update the index in the same change. Git already records what disappeared,
  when, and why.

  Apply each merge in this order: update the survivor, confirm it remains one
  focused topic, delete the poorer file, then update the index last. If any
  step fails, restore the touched memory files from git, leave the index
  unchanged, and report the failure.
- **Convert relative dates to absolute dates, anchored on the observation's
  own timestamp, never on today's session date.** An observation written
  with a `[YYYY-MM-DD] [Source]: ...` stamp is anchored to that date; resolve
  "next week", "this quarter", or "Friday" against the stamp. If an older
  observation carries no stamp, use file history only when the introducing
  commit plausibly represents the observation time. A bulk import, fixture
  creation, or commit date that conflicts with dates inside the file is not a
  valid anchor. Never resolve against the date this consolidation pass happens
  to run: a pass run months after the memory was written would silently shift
  every relative date forward by that gap and record a wrong date as if it
  were exact. If neither an inline stamp nor trustworthy file history anchors
  the phrase, do not guess: leave the relative date in place and flag it
  inline, for example
  `[AMBIGUOUS-DATE: no source stamp or file history for "next week"]`, for a
  human to resolve.
- **Drop facts that are cheap to re-fetch** from a calendar, a doc, or a
  connected tool: a meeting time, a ticket status, a file's current line
  count. Keep facts that are **hard to re-derive**: a stated preference, the
  reasoning behind a decision, who owns or should be contacted about
  something. The test is re-derivation cost, not topic.

### Phase 3: Tidy the Index

Update `.serena/memories/memory-index.md` in the same pass as the merges
above, so the index and the files it points to never fall out of sync:

- Keep the index under 200 lines and about 25 KB total. Measure it, do not
  eyeball it: `wc -l` and `wc -c` on `.serena/memories/memory-index.md`.
- Aim for one line per entry, each under about 150 characters, so the index
  stays scannable in a single read.
- Remove entries for deleted files and point useful keywords at the survivor.
  Move any surviving detail into the topic file itself, not into the index;
  the index is a lookup, not a second copy of the content.
- Add an index entry for anything Phase 2 made newly important (a merged
  file, a sharpened durable memory) that the index does not yet point to.

Finish the pass per the Output section below; do not restate its shape
here.

## Output

Finish with a short summary:

- Whether the pass completed.
- Number of files scanned, changed, and deleted.
- One line per changed file.
- Any unresolved `[AMBIGUOUS-DATE: ...]` flags or discovery failures.
- Final index line count and byte size.

## Verification

| Operation | Verification |
|-----------|---------------|
| Merge | Survivor contains every unique fact, remains one focused topic, poorer file is deleted, and index keywords point at the survivor |
| Deletion | `git diff -- .serena/memories/` shows only intended deletions and edits; deleted content remains recoverable from git |
| Relative dates converted | Every "next week", "this quarter", or bare weekday name is either an absolute date anchored on its source stamp or file history, or an explicit `[AMBIGUOUS-DATE: ...]` flag; none are guessed |
| Index tidy | `wc -l memory-index.md` <= 200 and `wc -c memory-index.md` <= ~25,600 (25 KB) |
| Summary produced | Final message states scanned, changed, and deleted counts, plus one line per changed file |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|------------------|
| Merging files that merely share a domain or index section | Merge only genuine duplicates about the same person, project, or preference; keep distinct atomic concepts separate |
| Resolving a relative date against today's session date | Anchor on the observation's own `[YYYY-MM-DD]` stamp or file history; flag if neither exists |
| Leaving "next week" or "this quarter" unresolved and unflagged | Resolve to an absolute date, or flag `[AMBIGUOUS-DATE: ...]` if no anchor exists |
| Growing the index with a fresh paragraph per entry | One line per entry, under about 150 characters, detail lives in the topic file |
| Recording a fact the user can re-fetch from a calendar or doc | Keep only what is hard to re-derive: preferences, decision context, ownership |

## Related Skills

| Skill | When to Use Instead |
|-------|----------------------|
| `memory` | Router for search, reflexion, gate, or maintenance operations |
| `curating-memories` | Forgetful-store curation: obsolete, deduplicate, link |
| `memory-maintenance` | Health check, token count, size validation, benchmark |
| `memory-search` | Tier 1 semantic lookup, not a consolidation pass |

If the project has no Serena memory tree, stop with a no-op summary.
