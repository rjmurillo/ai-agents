---
name: curating-memories
description: Maintain Serena memory files in place. Mark superseded content, keep current truth visible inline, and run the supersession sweep that proposes a disposition per file without editing it. Use when you say "how do I mark a memory obsolete", "how do I supersede a memory", or "run the supersession sweep". Do NOT use for merging or deleting Serena files or tidying Serena indexes; use memory-consolidate.
license: MIT
version: 2.0.0
---

# Curating Memories

Active curation keeps the knowledge base accurate. A memory that is fully
resolved or historical but still reads as live guidance forces a fresh agent
to read past archaeology to reach current truth, and outdated content pollutes
every search that touches it.

This skill owns in-file supersession markers on `.serena/memories/**`. It never
merges or deletes Serena files and never edits Serena index files. Use
`memory-consolidate` for cross-file merges, deletions, and index cleanup, and
`memory-maintenance` for health, token, and size checks.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `how do I mark a memory obsolete` | Strike the obsolete content, add a dated banner |
| `how do I supersede a memory` | Apply the healthy-supersession shape below |
| `how do I clean up stale memories` | Run the sweep, then verify each proposal |
| `run the supersession sweep` | Scripts section below |

## Scope

Serena memories are markdown files, not records in a store. There is no
soft-delete, no obsolete flag, and no link table to write. Curation is an edit
to the file's own text, and history survives because the file keeps it visible
rather than because a backend hides it.

| In scope | Out of scope |
|----------|--------------|
| Strike-through and dated banners inside one memory file | Merging two memory files (`memory-consolidate`) |
| Collapsing a resolved investigation to a changelog footer | Deleting a memory file (`memory-consolidate`) |
| Adding a dated-snapshot banner to a point-in-time doc | Editing `memory-index.md` (`memory-consolidate`) |
| Running and verifying the supersession sweep | Store health, token, and size checks (`memory-maintenance`) |

## When to Supersede

Supersede content when:

- Newer information contradicts it.
- A decision has been reversed or replaced.
- The code, script, workflow, or artifact it references no longer exists.
- The file records a resolved investigation but still reads as an open one.
- A dated point-in-time snapshot is framed as current state.

Do not supersede on style, length, or strikethrough density. A file that
already carries struck-through history with current truth visible is the
target shape, not a rot signal.

## Scripts: Supersession Sweep

The append-never-delete pattern is the failure this sweep targets: a memory
that is fully resolved or historical but still reads as live guidance, so a
fresh agent has to read past archaeology to reach current truth. Run the
sweep to surface those files. It **proposes** a disposition per file and
edits nothing; ratification is a separate, confirmed step.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/curating-memories/scripts/supersession_sweep.py"
```

Add `--json` for machine-readable output, or `--root <dir>` to scan a
directory other than `.serena/memories`.

### The four buckets

| Bucket | Signal | Action |
|--------|--------|--------|
| `live` | No supersession markers | Leave alone |
| `healthy-supersession` | Struck-through obsolete content plus a dated banner, current truth visible | Leave alone; this is the target shape |
| `resolved-or-historical-but-present` | `Status: RESOLVED`/`BLOCKING` co-present with references to removed artifacts or per-section `(Historical)` tags | Propose archive, or collapse to a one-line changelog footer |
| `temporal-snapshot-as-live` | A dated point-in-time doc framed as current state | Propose a dated-snapshot banner |

### The constraint (non-negotiable)

The sweep is a generator self-report, which is the closed-loop-validator
trap. The classification is a **routing signal into verification, never a
verdict**:

- The sweep proposes a disposition. It does not edit or delete.
- Ratify with the [doc-accuracy](../doc-accuracy/SKILL.md) code-as-source-of-truth
  discipline: archive a memory only after confirming the artifacts it
  references are actually gone and no live path depends on it.
- A human or a second independent check confirms before any content is
  removed. A mis-flag on a load-bearing entry is the exact loss this
  proposal-only design prevents.

### The healthy-supersession target shape

When you collapse a `resolved-or-historical-but-present` file, do not bury
it. Strike through the obsolete content, add a dated banner explaining why,
and keep current truth visible inline. `cost/cost-summary-reference.md` is
the exemplar: obsolete rows struck through, a dated `IMPORTANT` banner,
history preserved, nothing hidden. Strikethrough density alone is a
healthy-supersession signal, never a rot signal; the sweep will not propose
archiving a file on strikethrough count.

## Process

1. Run the sweep, or open the memory the user named.
2. Read the file and classify it against the four buckets.
3. Verify the proposal against the code: confirm the artifacts the file
   references are actually gone before treating it as historical.
4. Present the disposition to the user and wait for confirmation.
5. Edit the file to the healthy-supersession shape, keeping history visible.
6. Re-read the edited file and confirm current truth is reachable without
   reading the struck-through content.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Deleting obsolete content outright | Loses the audit trail and the reason the position changed | Strike it through under a dated banner |
| Treating a sweep bucket as a verdict | The sweep is a self-report; a mis-flag on a load-bearing memory is unrecoverable | Verify against the code, then confirm with the user |
| Archiving on strikethrough density | That is the healthy shape, not rot | Check for removed-artifact references and a resolved status |
| Editing `memory-index.md` from here | Index cleanup belongs to a different owner and the two passes conflict | Route to `memory-consolidate` |
| Burying superseded content in a collapsed footer with no date | A future reader cannot tell what changed or when | Date the banner and say why the content was superseded |

## Verification

After curation operations:

- [ ] Reconciliation: paste the sweep output line for each file you acted on, showing its bucket (not a claim about it)
- [ ] Every artifact a superseded file references was confirmed gone by an actual lookup, quoted in the output
- [ ] Each edited file still shows current truth inline without reading the struck-through content
- [ ] Every supersession carries a date and a one-line reason
- [ ] Curation changes were confirmed by the user before execution
- [ ] No memory file was merged, deleted, or removed from `memory-index.md` by this skill

## References

| Artifact | Relationship |
|----------|-------------|
| `.claude/skills/memory-consolidate/SKILL.md` | Owns cross-file merges, deletions, and index cleanup |
| `.claude/skills/memory-maintenance/SKILL.md` | Owns store health, token, and size checks |
| `.claude/skills/doc-accuracy/SKILL.md` | Code-as-source-of-truth discipline used to ratify a proposal |
| `.claude/skills/curating-memories/scripts/supersession_sweep.py` | The proposal-only classifier this skill drives |
