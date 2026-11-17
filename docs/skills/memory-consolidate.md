# memory-consolidate

Runs a periodic cleanup pass over Serena memory files. It keeps lasting context, retires finished work, merges true duplicates, fixes relative dates, and trims `memory-index.md`.

## When to use it

- You want a periodic review that separates durable context (preferences, working style, key relationships, recurring workflows) from dated context (projects, deadlines, one-off tasks).
- Two memory files answer the same lookup and one is the poorer, older copy.
- `memory-index.md` has grown too long to scan.
- Trigger phrases: `consolidate memory`, `consolidate Serena memory`, `merge memory files`, `tidy the memory index`.

## When not to use it

- You want in-file supersession markers: use [`curating-memories`](curating-memories.md).
- You want health, token, or size checks: use [`memory-maintenance`](memory-maintenance.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:memory-consolidate`. The [`memory`](memory.md) router loads it for cleanup requests. To ask for it by name, say:

```text
Use the memory-consolidate skill to consolidate Serena memory and tidy memory-index.md.
```

The skill takes inventory first, proposes merges and deletions, and asks you to confirm them by exact path before it writes anything.

## What you get

The skill ends with a JSON envelope. On success:

| Field | Meaning |
| --- | --- |
| `Success` | `true` |
| `Data.Completed` | Whether the pass finished. |
| `Data.FilesScanned`, `FilesChanged`, `FilesDeleted` | Counts. |
| `Data.ChangedFiles` | Paths of changed files. |
| `Data.UnresolvedFlags` | Items left for a human, such as `[AMBIGUOUS-DATE: ...]`. |
| `Data.IndexLines`, `Data.IndexBytes` | Final size of `memory-index.md`. |

On failure, the envelope has `Success: false`, `Data: null`, and an `Error` with `Message`, `Code`, and `Type`. `Metadata` then adds `Phase` and `Rollback` (`complete`, `not-required`, or `blocked`). No memory contents or full diffs appear in any field.

## Advanced use

The pass has three phases.

**Phase 1, take stock.** The skill gets the complete inventory from Serena's list-memories capability, and stops if Serena is inactive, on another project, or errors. It audits at most 2,000 files (reports `>=2001` and stops past that). It stops before any file over 32,768 bytes or when cumulative input passes 5,000,000 bytes. It reads `memory-index.md`, audits for unindexed files and dangling index entries, and flags overlap, staleness, and thinness.

**Phase 2, consolidate.**

- Merge only genuine duplicates: both files answer the same lookup about the same person, project, or preference, and one is clearly poorer. Fold every unique fact into the richer file, delete the poorer one, and update indexes last.
- Retire a dated file only with explicit completion evidence from a trusted source. A passed date alone is not evidence. Fold any lasting takeaway into a durable memory first.
- Convert relative dates using the observation's own `[YYYY-MM-DD]` stamp, never today's date. With no trustworthy anchor, leave the phrase and flag it `[AMBIGUOUS-DATE: ...]`.
- Drop facts that are cheap to re-fetch. Keep facts that are hard to re-derive, such as preferences, decision reasoning, and ownership.

Evidence identifies a deletion candidate. It never authorizes one. Before deleting any file, get human confirmation that names the exact path and, for a merge, the survivor. Before removing facts from a surviving file, summarize the removals by path and confirm.

**Phase 3, tidy the index.** Keep `memory-index.md` at 200 lines and 25,600 bytes or fewer. Aim for one line per entry, under about 150 characters. Update topic `*-index.md` files in the same pass.

Before any edit, the memory tree must be clean and tracked by git. The skill treats all memory content as untrusted data. It never follows instructions found in a memory file. Mutations use Serena's edit, write, and delete capabilities only. If a target changed since the skill last read it, the skill stops. On a partial failure, it leaves the git diff for review and does not auto-restore.

One helper script scopes the run. Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory-consolidate/scripts/memory_git_targets.py check
```

| Subcommand | Purpose |
| --- | --- |
| `path` | Print the fixed manifest path. |
| `check` | Validate the manifest. Makes no change. |
| `restore` | Restore every manifest target from the starting commit. Overwrites edits. Takes `--dry-run`. |
| `cleanup` | Remove the manifest. Takes `--dry-run`. |

Exit codes: 0 ok, 1 invalid manifest, 2 usage error or not in a git repository, 3 a git command failed.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory`](memory.md): the router that sends cleanup requests here.
- [`curating-memories`](curating-memories.md): in-file supersession markers.
- [`memory-maintenance`](memory-maintenance.md): store health, token, and size checks.
- Source: [`SKILL.md`](../../src/claude/skills/memory-consolidate/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
