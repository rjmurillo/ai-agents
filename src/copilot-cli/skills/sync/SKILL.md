---
name: sync
version: 1.0.0
description: Detect Spec-to-Code drift by scanning REQ, DESIGN and TASK specs for references to code that no longer exists, then report it for triage. Use when you say `detect spec drift`, `sync the specs`, or `did my refactor break a spec`, and run it after a hand-edit that moved or deleted code. Do NOT use to write a spec (use spec), and do NOT use to auto-rewrite specs; it reports and never edits.
license: MIT
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(python3 scripts/sync/detect_spec_drift.py*)
argument-hint: spec-tier-or-empty
user-invocable: true
---

# Sync

<!-- vendor-portability: contributor-facing drift detector for the rjmurillo/ai-agents
     repo itself. It runs scripts/sync/detect_spec_drift.py over that repo's own
     spec tiers under .agents/specs/requirements, .agents/specs/design and
     .agents/specs/tasks. The sync-log artifacts named under Step 3 are a planned
     follow-up and no such directory exists yet.
     None of those ship in a plugin root, so this skill's audience is repo
     contributors, not plugin consumers (ADR-083, issue #5632). -->

<!-- vendor-portability-exec: the three python3 invocations below run
     scripts/sync/detect_spec_drift.py, which is the skill. A prose declaration
     does not exempt an executable invocation, which migrates independently
     (issue #2838), so the dependency is declared here too. -->

Migrated from the sync command under ADR-064, which makes skills the single
user-invocable surface. The command file is gone, so its path is named here in
plain text rather than as a citation to something a reader could open.

The forward path (`/spec` -> `/plan` -> `/build`) turns intent into code. There is no clean reverse path. When you hand-edit code (refactor, hotfix, taste change), the spec drifts silently and the staleness surfaces only at `/review` time, late and often misattributed as "the spec was wrong" instead of "the spec needs updating". `/sync` closes that loop: it finds the drift while you still remember why you made the change.

## What this slice does

This command detects Spec->Code drift and reports it. It does NOT auto-rewrite specs. Detection runs; patch proposal is a follow-up (see Step 3).

## Triggers

| Phrase | Action |
|--------|--------|
| `/sync` | Scan all spec tiers for stale code references |
| `/sync .agents/specs/design` | Scan one spec tier |
| `detect spec drift` | Run the detector and report drift |

## Arguments

Sync: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If `$ARGUMENTS` names a spec tier, scan that tier only by passing it to
`--target`. Otherwise scan all three tiers.

## Process

### Step 1: Detect drift

Run the drift detector against the specification tier:

```bash
python3 scripts/sync/detect_spec_drift.py --output-format human
```

The detector scans `.agents/specs/requirements`, `.agents/specs/design`, and `.agents/specs/tasks` for backticked references to code and artifact paths rooted at any of its known trees (the scripts, build, skills, commands, templates, tests and source roots; the authoritative list is the detector's own). Each reference is resolved against the working tree. A reference to a path absent on disk is drift: the spec points at code that moved or was deleted.

To scan one tier only, pass `--target`:

```bash
python3 scripts/sync/detect_spec_drift.py --target .agents/specs/design --output-format human
```

Exit codes (per ADR-035): `0` no drift, `1` drift found, `2` configuration error. Unsafe `--target` values (absolute paths, `..`, or symlink escapes) return exit `2`. Unsafe spec references are reported as drift instead of probing outside the repo.

### Step 2: Triage the findings

For each `DRIFT` line the detector reports (`spec_file:line -> path absent on disk`), decide which case applies:

- **Code moved**: the path was renamed. Update the spec reference to the current path.
- **Code deleted**: the capability was removed. Update the spec to reflect the removal, or restore the code if the removal was unintended.
- **Intentional forward reference**: the spec names a planned path that does not exist yet. Mark the line with a trailing `<!-- sync-drift-ignore -->` so the detector skips it.
- **Unsafe reference**: the spec uses `..`, an absolute path, or a symlink escape. Treat it as drift and update the spec to a repo-contained path.

Do not auto-apply edits. Confirm each case with the author of the change before touching the spec.

### Step 3: Propose spec patches (follow-up, not in this slice)

Patch proposal via the `spec-generator` agent is tracked as a follow-up. When wired, `/sync` will hand the drift findings to `agent_type: "project-toolkit:spec-generator"` to draft REQ/DESIGN/TASK edits and write a sync-log record, in a directory alongside the spec tiers, carrying the commit range it covered. Until then, apply the triage from Step 2 by hand and record the rationale in the PR description.

## Principles

- **Propose, do not auto-apply.** A human approves every spec edit. The detector flags; it never rewrites.
- **Detection is deliberate, not real-time.** Run `/sync` after a hand-edit. Real-time drift detection during `/build` is a `PostToolUse` hook concern, out of scope here.
- **The spec is a source of truth.** Drift erodes that. Catching it early keeps the spec defensible for "what does this code actually do" questions.

## Output

No em dashes or en dashes in anything this skill writes.
Use commas, periods, colons, parentheses, hyphens, or restructure.

- The detector's `VERDICT` line (`PASS` or `DRIFT`) and per-finding `spec_file:line -> path` list.
- A triage decision per finding (moved / deleted / intentional).
- The spec edits applied or proposed, with rationale recorded in the PR description.

## Verification

A gate is any check whose failure would falsify your conclusion. Only a current result on the exact state and scope clears it. Failure, timeout, stale run, skip, or subset leaves the claim unproved. Say what ran and what returned. If blocked, name who can clear it.

- [ ] Detector exits `0` only when no drift exists.
- [ ] Detector exits `1` when stale references exist.
- [ ] Detector exits `2` for unsafe targets, unreadable specs, or missing custom targets.
- [ ] The generated Copilot mirror matches this source.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Treating unreadable specs as clean | Hides drift behind an I/O failure | Fail closed with exit `2` |
| Scanning absolute or parent targets | Walks outside the repository | Reject unsafe targets |
| Auto-rewriting specs | Changes source of truth without review | Report drift and require author triage |

## Extension Points

- Patch proposal via `spec-generator`.
- Additional reference roots in `scripts/sync/detect_spec_drift.py`.
- Sync log artifacts, in a directory alongside the spec tiers. Named without a path here on purpose: no such directory exists yet, and a citation to one would point at nothing.
