# curating-memories

Marks outdated content in a Serena memory file as superseded, in place. It keeps current truth visible and runs a sweep that proposes what to do with each file, without editing any of them.

## When to use it

- A memory records a resolved investigation but still reads as an open one.
- A decision was reversed, or the code, script, or workflow a memory cites no longer exists.
- A dated point-in-time snapshot reads as current state.
- Trigger phrases: `how do I mark a memory obsolete`, `how do I supersede a memory`, `how do I clean up stale memories`, `run the supersession sweep`.

## When not to use it

- You want to merge or delete memory files, or tidy indexes: use [`memory-consolidate`](memory-consolidate.md).
- You want store health, token, or size checks: use [`memory-maintenance`](memory-maintenance.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:curating-memories`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the curating-memories skill to run the supersession sweep on .serena/memories and show me the proposals.
```

The skill runs the sweep, checks each proposal against the code, and asks you to confirm before it edits anything.

## What you get

The sweep sorts every memory file into one of four buckets:

| Bucket | Signal | Action |
| --- | --- | --- |
| `live` | No supersession markers | Leave alone. |
| `healthy-supersession` | Struck-through obsolete content, a dated banner, and current truth visible | Leave alone. This is the target shape. |
| `resolved-or-historical-but-present` | `Status: RESOLVED` or `BLOCKING` next to references to removed artifacts, or per-section `(Historical)` tags | Propose archive, or collapse to a one-line changelog footer. |
| `temporal-snapshot-as-live` | A dated point-in-time doc framed as current state | Propose a dated-snapshot banner. |

An edited file strikes through the obsolete content, adds a dated banner that says why, and keeps current truth readable without the struck-through text.

## Advanced use

The sweep proposes and never edits. Treat each bucket as a routing signal, not a verdict. Verify a proposal against the code with the [`doc-accuracy`](doc-accuracy.md) discipline: archive a memory only after you confirm the artifacts it cites are gone and no live path depends on it. A human or a second independent check confirms before any content is removed. Strikethrough density alone is never a reason to archive.

Run the sweep from the root of a checkout of this repository:

```bash
uv run python .claude/skills/curating-memories/scripts/supersession_sweep.py --root .serena/memories --json
```

| Flag | Meaning |
| --- | --- |
| `--root` | Directory of memory files to scan. Default is `.serena/memories`. |
| `--json` | Emit the proposal report as JSON. |
| `--include-live` | With `--json`, also list `live` and `healthy-supersession` files. By default the JSON lists only actionable proposals. Counts always cover every file. |

The script always exits 0, because the sweep proposes and never gates.

The skill never merges or deletes memory files and never edits `memory-index.md`. Its process: run the sweep or open the named memory, classify it, verify against the code, present the disposition and wait for confirmation, edit to the healthy-supersession shape, then re-read the file.

[`reflect`](reflect.md) routes conflicting or stale learnings here.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory-consolidate`](memory-consolidate.md): cross-file merges, deletions, and index cleanup.
- [`memory-maintenance`](memory-maintenance.md): store health, token, and size checks.
- [`doc-accuracy`](doc-accuracy.md): the code-as-source-of-truth check used to ratify a proposal.
- [`reflect`](reflect.md): invokes this skill for stale learnings.
- Source: [`SKILL.md`](../../src/claude/skills/curating-memories/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
