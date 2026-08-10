---
name: memory-consolidate
version: 0.1.0
description: Reflective consolidation pass over Serena memory files, the fifth
  operation sibling of the memory router per ADR-063. Separates durable
  context (preferences, working style, key relationships, recurring
  workflows) from dated context (projects, deadlines, one-off tasks), merges
  overlapping topic files onto the richer path, converts relative dates to
  absolute ones, and tidies memory-index.md so a future session orients fast
  without re-asking. Use when you say `consolidate memory`, `consolidate
  Serena memory`, `merge memory files`, or `tidy the memory index`. Do NOT
  use for Forgetful-store curation (use curating-memories) or health, token,
  or size checks (use memory-maintenance).
license: MIT
metadata:
  adr: ADR-007, ADR-037, ADR-056, ADR-063
  type: operation
  parent: memory
---

# Memory Consolidate

Reflective consolidation operation for the tiered memory system, split out of
the `memory` router per ADR-063 (memory-skill decomposition; target shape is
3 to 5 operation siblings, and this is the fifth). `memory` still routes
here; an agent doing a periodic memory cleanup loads this sub-skill instead
of the full router.

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

1. **Memory skills first.** Use `memory-search` to rank and list topic files
   by keyword, and `curating-memories`'s supersession sweep (below) to
   classify a file before you touch it.
2. **Serena MCP second.** When a skill does not cover the check you need,
   call `mcp__serena__list_memories` and `mcp__serena__read_memory` directly.
   Phase 1 below states what `list_memories` does and does not enumerate;
   see `.serena/memories/README.md`, "Directory Structure" for the full
   contract; do not restate it here.
3. **Direct directory access third.** Only when the above are unavailable,
   read `.serena/memories/` and its topic subdirectories directly. The one
   exception is Phase 1's bounded stale-index audit, which always compares
   relevant subdirectory filenames with their index entries, even when a
   higher discovery tier succeeded. The directory and index contract is
   owned by `.serena/memories/README.md`; do not restate it here, read it.

These three tiers govern discovery only: how you find out which memory files
exist. The canonical scripts in Phase 1 below (the supersession sweep, the
token count, and the size check) are not part of this fallback chain. They
operate on file paths discovery already produced, so run them regardless of
which tier surfaced that list.

## Process

### Phase 1: Take Stock

1. List the top-level memory files (`memory-search`'s index lookup,
   `mcp__serena__list_memories`, or direct `ls .serena/memories` per the Tool
   Order above) and read `memory-index.md` in full. `mcp__serena__list_memories`
   enumerates top-level files only: atomic topic memories in subdirectories
   are hidden from it (`.serena/memories/README.md`, "Directory Structure").
   A plain `ls` at this step has the same indexes-only limitation, so read
   each relevant `*-index.md` next and use the paths it names to reach and
   skim the atomic memories themselves
   (`mcp__serena__read_memory("topic/memory-name.md")` or, as a fallback,
   direct file reads under `.serena/memories/topic/`). Fall back to listing a
   subdirectory's contents directly only when its index looks stale or
   incomplete against what the directory actually holds. Then perform one
   bounded stale-index audit regardless of discovery tier: compare each
   relevant topic directory's Markdown filenames with its `*-index.md`
   entries. Add unindexed files to the Phase 1 inventory and record dangling
   index entries as errors.
2. Classify every topic file with the supersession sweep, without editing
   anything. Run this regardless of which discovery tier above produced the
   file list:

   ```bash
   uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/curating-memories/scripts/supersession_sweep.py"
   ```

   Its own docstring is explicit that "Exit code is always 0: this is a
   proposal, not a gate," owned and documented by the `curating-memories`
   skill (the invocation above is the portable, install-root-relative form;
   do not hardcode a `.claude/` path or link to the script file directly).
   See [`curating-memories/SKILL.md`, "The four buckets"](../curating-memories/SKILL.md)
   for what each classification means; do not restate the buckets here.
   Treat its output as a routing signal into Phase 2, never as a verdict, the
   same discipline `curating-memories` documents for its own callers.
3. Skim each file for three signals beyond what the sweep reports: **overlap**
   (two or more files cover the same person, project, or preference),
   **staleness** the sweep did not catch (a one-off task that quietly passed
   its date), and **thinness** (a file that does not earn its own retrieval
   cost). Judge thinness and its opposite, oversize, against the per-file
   atomicity thresholds in `.serena/memories/README.md`, "Size Constraints";
   do not restate the numbers here. Confirm with the canonical scripts
   rather than eyeballing:

   ```bash
   python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/count_memory_tokens.py" "<file>"
   python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/test_memory_size.py" .serena/memories --pattern "*.md"
   ```

### Phase 2: Consolidate

Separate what you found in Phase 1 into two buckets:

- **Durable**: preferences, working style, key relationships, recurring
  workflows. Keep these, and sharpen them: cut hedging, cut anything the
  sweep or your own read marked resolved, keep the current statement of the
  preference or relationship without changing its recorded meaning. This is
  an in-place content edit under the `memory` skill's own Serena Write
  Conventions; it needs no separate ratification.
- **Dated**: projects, deadlines, one-off tasks. When a dated memory has
  passed or completed, propose archiving it, do not archive it yourself: the
  supersession sweep's `resolved-or-historical-but-present` bucket is the
  routing signal for exactly this case, and the same human-confirmed
  ratification rule below applies. If the memory carries a lasting takeaway
  (a preference the project revealed, a contact the project introduced),
  fold only that takeaway into the relevant durable memory now, before the
  archival proposal is ratified.

Apply these edits with one non-negotiable constraint: **this skill never
physically deletes a memory file, and it never claims authority to.**
Editing content in place (sharpening a durable memory, striking through
obsolete text) is permitted directly under the `memory` skill's Serena Write
Conventions. Removing a file from disk is not the same operation: it is an
archival decision that curating-memories and `doc-accuracy` both gate behind
a separate, human-confirmed (or independently second-checked) ratification
step, because a mis-flagged file is unrecoverable the moment it is gone. This
skill proposes; it does not ratify.

- **Merge only genuine duplicates.** Two files are merge candidates only
  when they would both answer the same lookup query about the same person,
  project, or preference, and one is clearly the poorer, superseded version
  of the other. Sharing a domain, sitting in the same index section, or
  being topically adjacent is not enough: never combine two distinct atomic
  concepts (for example, a contact's communication preference and an
  unrelated project's status) just because they overlap in some other way.
  `.serena/memories/README.md`'s atomicity thresholds exist to keep one
  retrievable concept per file; a merge that violates that is a regression,
  not a consolidation.

  When you find a genuine duplicate: identify the richer path (more
  current, more cross-linked, more concrete content), fold every unique fact
  from the poorer file into it, then apply the healthy-supersession pattern
  to the poorer file in place, the same target shape curating-memories
  documents for its own callers: strike through the obsolete content, add a
  dated banner pointing at the survivor, and leave current truth visible
  rather than hidden (`curating-memories/SKILL.md`, "The healthy-supersession
  target shape"). Add the `supersedes` relation on the survivor, pointing at
  the file that is still on disk. Propose the poorer file's eventual
  physical removal in the closing Output section; do not perform it. If a
  later, separately ratified change does remove a file, that change must
  update or delete every `supersedes` reference that pointed at it in the
  same change, so no reference is left dangling.

  Apply each merge as a small recoverable transaction: update the survivor
  first, run the size check, mark the poorer file as healthy-supersession,
  then redirect the index last. If any write or check fails, restore every
  touched file from its pre-edit content, leave the index unchanged, and
  report the failure in `Error`. A rerun starts from the unchanged index and
  repeats the same candidate.
- **Convert relative dates to absolute dates, anchored on the observation's
  own timestamp, never on today's session date.** An observation written
  under the `memory` skill's Source Tracking convention carries a
  `[YYYY-MM-DD] [Source]: ...` stamp; resolve "next week", "this quarter", or
  "Friday" against that stamp. If an older observation carries no stamp,
  anchor on recoverable file history instead (for example, the commit that
  introduced the line). Never resolve against the date this consolidation
  pass happens to run: a pass run months after the memory was written would
  silently shift every relative date forward by that gap and record a wrong
  date as if it were exact. If neither an inline stamp nor file history
  anchors the phrase, do not guess: leave the relative date in place and
  flag it inline, for example
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

- Keep the index under 200 lines and about 25 KB total. This user-set
  heuristic is this skill's own operational budget for the top-level index,
  not a repository-wide threshold. It is separate from the per-file
  atomicity thresholds quoted in Phase 1. Measure it, do not eyeball it:
  `wc -l` and `wc -c` on `.serena/memories/memory-index.md`.
- Aim for one line per entry, each under about 150 characters, so the index
  stays scannable in a single read.
- Point retired-in-place and merged entries at the survivor. A file marked
  healthy-supersession in Phase 2 still exists on disk, so the index should
  redirect to the current-truth survivor rather than dropping the entry
  outright; only drop an entry once a separately ratified change has
  actually removed the file it pointed to. Move any surviving detail into
  the topic file itself, not into the index; the index is a lookup, not a
  second copy of the content (`.serena/memories/README.md`, "Index File
  Format").
- Add an index entry for anything Phase 2 made newly important (a merged
  file, a sharpened durable memory) that the index does not yet point to.

Finish the pass per the Output section below; do not restate its shape
here.

## Output

This sub-skill emits ADR-056's standard envelope (ADR-056, "Decision":
"**All skill scripts MUST wrap output in a standard envelope** with
`Success`, `Data`, `Error`, and `Metadata` fields"). Different than the
canonical form: ADR-056 targets scripts with a `-OutputFormat` switch
between JSON and human text; this sub-skill has no script of its own to
carry that switch, so it emits the same four fields as the closing chat
message instead of a JSON payload:

- **Success**: the pass completed Phases 1 through 3 with no unresolved
  blocker, for example a relative date left unflagged or a merge proposed
  without a richer-path check.
- **Data**: the number of files touched (merged in place, sharpened, or
  proposed for archival), and a one-line change per file.
- **Error**: any `[AMBIGUOUS-DATE: ...]` flag left unresolved, or a
  discovery tier that failed and had to be reported instead of silently
  skipped.
- **Metadata**: counts a caller can check without re-reading the memory
  tree, for example files scanned, files touched, and the index line count
  after Phase 3.

Name any proposed physical deletion explicitly as a proposal awaiting
ratification, not a completed action. This is the artifact the next session
reads to confirm the pass happened and to know what moved.

## Verification

| Operation | Verification |
|-----------|---------------|
| Supersession sweep run | Command exits 0; buckets for every scanned file present in output |
| Merge | Survivor carries a `supersedes` relation pointing at a file that still exists; the poorer file shows struck-through content plus a dated banner (healthy-supersession), not deletion |
| Physical deletion | Never performed by this skill; proposed in the Output section for a separate human-confirmed or independently second-checked ratification |
| Relative dates converted | Every "next week", "this quarter", or bare weekday name is either an absolute date anchored on its source stamp or file history, or an explicit `[AMBIGUOUS-DATE: ...]` flag; none are guessed |
| Index tidy | `wc -l memory-index.md` <= 200 and `wc -c memory-index.md` <= ~25,600 (25 KB) |
| Size validation | `test_memory_size.py` exits 0 against `.serena/memories` after the pass |
| Summary produced | Final message states files-touched count and a one-line change per file |

## Anti-Patterns

| Anti-Pattern | Do This Instead |
|--------------|------------------|
| Trusting the sweep's label as a verdict | Confirm against the file's own content before merging or proposing archival |
| Deleting a file yourself during consolidation | Mark it healthy-supersession in place; propose removal for separate ratification |
| Creating a `supersedes` reference to a file you deleted | Keep the file in place until a ratified change removes it and updates the reference in the same change |
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
| `doc-accuracy` | Ratifying that an artifact a memory references is actually gone |

## References

- ADR-007: Memory-first architecture (Serena canonical, degrade-not-fail posture)
- ADR-037: Memory router architecture (the router pattern this operation joins)
- ADR-056: Skill output format standardization (the envelope this sub-skill
  emits; see Output)
- ADR-063: Memory skill decomposition (this extraction; fifth operation sibling)
- `.serena/memories/README.md`: directory structure, size constraints, index
  file format, and the quarterly curation process this operation runs ad hoc
- `.claude/skills/memory/SKILL.md`: the router; owns the canonical scripts and
  the Serena Write Conventions this operation edits under
- `.claude/skills/curating-memories/SKILL.md`: the supersession sweep this
  operation runs in Phase 1

<!-- vendor-portability: declared. This skill reads and writes .serena/memories/**
in the consumer's own project. A vendored install without a .serena/ tree has
nothing to consolidate yet; that is a no-op, not a broken run. Issue #2050,
ADR-063. -->
