---
name: sync
description: Detect Spec<->Code drift. Scan REQ/DESIGN/TASK specs for references to code that no longer exists, then report drift for review. Run after a hand-edit that moved or deleted code.
argument-hint:
  - spec-tier-or-empty
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(python3 scripts/sync/detect_spec_drift.py*)
user-invocable: true
---

# Sync Command

Sync: $ARGUMENTS

The forward path (`/spec` -> `/plan` -> `/build`) turns intent into code. There is no clean reverse path. When you hand-edit code (refactor, hotfix, taste change), the spec drifts silently and the staleness surfaces only at `/review` time, late and often misattributed as "the spec was wrong" instead of "the spec needs updating". `/sync` closes that loop: it finds the drift while you still remember why you made the change.

## What this slice does

This command detects Spec->Code drift and reports it. It does NOT auto-rewrite specs. Detection runs; patch proposal is a follow-up (see Step 3).

## Step 1: Detect drift

Run the drift detector against the specification tier:

```bash
python3 scripts/sync/detect_spec_drift.py --output-format human
```

The detector scans `.agents/specs/requirements`, `.agents/specs/design`, and `.agents/specs/tasks` for backticked references to code and artifact paths (`scripts/...`, `build/scripts/...`, `.claude/skills/...`, `.claude/commands/...`, `templates/...`, `tests/...`, `src/...`). Each reference is resolved against the working tree. A reference to a path absent on disk is drift: the spec points at code that moved or was deleted.

To scan one tier only, pass `--target`:

```bash
python3 scripts/sync/detect_spec_drift.py --target .agents/specs/design --output-format human
```

Exit codes (per ADR-035): `0` no drift, `1` drift found, `2` configuration error.

## Step 2: Triage the findings

For each `DRIFT` line the detector reports (`spec_file:line -> path absent on disk`), decide which case applies:

- **Code moved**: the path was renamed. Update the spec reference to the current path.
- **Code deleted**: the capability was removed. Update the spec to reflect the removal, or restore the code if the removal was unintended.
- **Intentional forward reference**: the spec names a planned path that does not exist yet. Mark the line with a trailing `<!-- sync-drift-ignore -->` so the detector skips it.

Do not auto-apply edits. Confirm each case with the author of the change before touching the spec.

## Step 3: Propose spec patches (follow-up, not in this slice)

Patch proposal via the `spec-generator` agent is tracked as a follow-up to issue #1997. When wired, `/sync` will hand the drift findings to `Task(subagent_type="spec-generator")` to draft REQ/DESIGN/TASK edits and write a record under `.agents/specs/sync-log/` with the commit range it covered. Until then, apply the triage from Step 2 by hand and record the rationale in the PR description.

## Principles

- **Propose, do not auto-apply.** A human approves every spec edit. The detector flags; it never rewrites.
- **Detection is deliberate, not real-time.** Run `/sync` after a hand-edit. Real-time drift detection during `/build` is a `PostToolUse` hook concern, out of scope here.
- **The spec is a source of truth.** Drift erodes that. Catching it early keeps the spec defensible for "what does this code actually do" questions.

## Output

- The detector's `VERDICT` line (`PASS` or `DRIFT`) and per-finding `spec_file:line -> path` list.
- A triage decision per finding (moved / deleted / intentional).
- The spec edits applied or proposed, with rationale recorded in the PR description.
