---
name: retro
description: Fill an unfilled auto-retro skeleton for a date by running the retrospective skill
argument-hint: fill <YYYY-MM-DD>
allowed-tools: Skill, Read, Glob
user-invocable: true
---

# Retro Command

Fill an unfilled auto-retrospective skeleton. The Stop hook
(`.claude/hooks/Stop/invoke_auto_retrospective.py`) writes a skeleton on
session end and stamps it with the marker `<!-- RETRO-STATE: skeleton-pending-fill -->`.
The SessionStart context loader counts those skeletons and points you here.
See Issue #2079.

## Triggers

| Trigger phrase | Behavior |
|----------------|----------|
| `/retro fill {date}` | Fill the skeleton at .agents/retrospective/{date}-auto-retro.md |
| `/retro fill` | Prompt for the date, then fill |
| `/retro` | List pending (marker-bearing) skeletons and stop |
| `retro fill` | Same as the fill operation, when invoked by name |
| `fill retro skeleton` | Same as the fill operation |

## Arguments

`$ARGUMENTS` carries the operation and the date, for example `fill 2026-06-03`.

- `fill <YYYY-MM-DD>`: fill the skeleton at
  `.agents/retrospective/<YYYY-MM-DD>-auto-retro.md`.

## Process

1. Parse `$ARGUMENTS`. The first token is the operation; for `fill`, the second
   token is the date in `YYYY-MM-DD` form.
   - If no operation is given, list pending skeletons: glob
     `.agents/retrospective/*.md`, read each, and report the ones whose body
     still contains `<!-- RETRO-STATE: skeleton-pending-fill -->`. Stop.
   - If the operation is `fill` but the date is missing or not `YYYY-MM-DD`,
     ask for the date. Stop.
2. Resolve the target file `.agents/retrospective/<date>-auto-retro.md`.
   - If it does not exist, say so and list the dates that do have skeletons.
     Stop.
   - If it exists but no longer contains the marker, it was already filled.
     Say so and stop; do not overwrite a completed retrospective.
3. Invoke the retrospective skill with the `retro fill` operation, passing the
   target file as scope. Use `Skill(retrospective)` with the trigger phrase
   `retro fill` and the date. The skill loads the skeleton, runs its Phase 0..5
   workflow over the session evidence for that date, overwrites the placeholder
   sections in place, and removes both the UNFILLED banner and the
   `<!-- RETRO-STATE: skeleton-pending-fill -->` marker so the SessionStart
   reminder stops surfacing the file.

The retrospective skill owns the workflow. This command only parses the
arguments, resolves the file, and hands off. Do not re-implement the
retrospective workflow here.

## Verification

- [ ] The target `.agents/retrospective/<date>-auto-retro.md` exists.
- [ ] After filling, the file no longer contains
      `<!-- RETRO-STATE: skeleton-pending-fill -->`.
- [ ] After filling, the file no longer contains the `UNFILLED SKELETON` banner.
- [ ] The next SessionStart no longer lists this date as pending.

## Anti-Patterns

- Re-implementing the retrospective workflow inside this command. Hand off to
  the `retrospective` skill instead.
- Overwriting a retro that was already filled (no marker present). Stop and
  report instead.
- Filling a date with no skeleton file. List the available dates and stop.

## Extension Points

- New operations (for example `list` or `archive`) extend the `## Process`
  parser; keep each operation thin and delegate analysis to the `retrospective`
  skill.
