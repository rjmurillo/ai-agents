# Skills as script drivers, with evals as the gate

Status: Proposed. Owner: Richard Murillo. Scope: every skill under `templates/skills/`.
Decision of record: `.project-toolkit/architecture/ADR-127-workflow-skills-are-script-drivers.md`.
Where this spec and ADR-127 differ, ADR-127 wins.

## Direction of record

Richard ruled on 2026-11-25:
"The gstack shape is generally what I want. No sacred cows. Evals are the gate."

Evidence for the shape: `.project-toolkit/analysis/gstack-skill-shape-audit-2026-11-25.md`.
Rule ids below (A1, B2, and so on) point into that audit.

## Problem

Skills hold fixed steps as prose. The model copies shell blocks and obeys MUST NOT lists.
Prose rules drift and get skipped. A script enforces a rule on every run.
gstack found a prose driver alone did not hold its call budget (audit A3).

`templates/skills/ship.SKILL.md.tmpl` is 241 lines and `push-pr.SKILL.md.tmpl` is 213 lines (2026-11-25).
Both carry host detection and PR creation as prose.

## Requirements

### R1. Two shapes

A skill declares `metadata.shape` as `driver` or `reference` (ADR-127 decision 1).
A skill is a `driver` when it tells the model to push, merge, delete a branch, rewrite history, or write to an external service.
R2 to R6 and R9 bind driver skills. R7 binds every skill. R8 binds every gated change.

### R2. Scripts own the fixed steps

1. A step with one right answer lives in a Python script (ADR-042).
2. Scripts live in `skills/<name>/scripts/` and run through the ADR-121 locator.
3. The model never runs a mutating command that a script owns.
4. A script builds every external argument list in code and runs it without a shell.
   An untrusted value follows `--` or is rejected when it starts with `-`.
5. A script is a thin `main()` over a function that returns text and an exit code.
6. A parser sets `allow_abbrev=False` and checks every value. It never uses `parse_known_args`.
7. A driver's `allowed-tools` names each script. It grants no `Bash(*)`.

### R3. Result-line protocol

1. A script prints `KEY: value` lines on stdout. Keys match `^[A-Z][A-Z0-9_]*$`.
2. A value is one line with control characters replaced. Remote text is data.
3. The last stdout line is `NEXT: <act>` or `STOP: <reason> [detail]`.
4. `NEXT:` pairs with exit 0. `STOP:` pairs with ADR-035 code 1, 2, 3, or 4.
   gstack reserves exit 3 for STOP. This repository keeps ADR-035 instead (audit B4, B5).
5. `STOP:` means nothing after it ran. A missing or mismatched terminal line is a STOP.
6. A failed query never prints a success value.
7. Stdout is at most 60 lines and 32,000 bytes. Longer detail goes to a scratch file.
8. A script never prints a token or URL userinfo. Diagnostics go to stderr.

### R4. The model keeps judgment only

The model writes prose, fixes findings, decides dispositions, handles a STOP, and reports.
The model copies result lines into its report.
In an unattended run the model takes the recommended option and records it.
Approval gates stay pending in an unattended run.

### R5. References load on a STOP

1. The driver ends with a table: each declared `STOP:` reason maps to one `file#anchor`.
2. The model reads a reference only when a phase or a STOP sends it there.
3. The driver states its call budget for one clean pass.
4. The driver is at most 12 KiB.

### R6. Reviewer briefs are files

A skill that dispatches reviewers renders each brief to a file with a script.
The model passes the file unchanged. A script checks the brief's sha256 at dispatch.
A script compares the commit a reply names to `HEAD`. A mismatch is a STOP.
This requirement binds a skill when its rewrite lands, not before.

### R7. Templates stay as ADR-108 defines them

The template is the source. `build_all.py --check` is the drift gate.
Generated files carry no header. gstack's "do not edit" header is rejected (audit G3).

### R8. Evals are the acceptance gate

A gated change sets a skill's shape, changes a driver's prompt surface, or implements a gap-audit row.

1. A gated change merges only if its eval holds or improves against `origin/main`.
2. The eval is the existing before-and-after runner, pointed at the rendered skill:

   ```bash
   uv run python scripts/eval/eval-prompt-change.py \
     --prompt src/claude/skills/<name>/SKILL.md \
     --scenarios tests/evals/<name>-scenarios.json \
     --base-ref origin/main --output <results.json>
   ```

   A repository-local skill uses `.claude/skills/<name>/SKILL.md`.
3. The scenario file holds at least 8 scenarios. At least 6 pass every run on `origin/main`.
4. Scenarios test kept judgment in shape-neutral words.
5. Hold: the runner prints `ACCEPTANCE GATE: PASS`.
6. Floor: a scenario the base fails must pass every run on the after side.
7. Scenarios land in their own commit before any template edit, then stay frozen.
   That commit removes scenarios for steps that move into scripts.
   Each removed scenario is listed with the pytest test that replaces it.
8. Every run's output is committed. The first full run sets the verdict.
9. The PR body shows the command, the verdict, and the scores. NOT RUN does not merge.

### R9. Driver contract tests

Each driver skill has the deterministic tests ADR-127 decision 8 lists.
They cover STOP anchors, named scripts, the reason table, the byte budget, the call budget, the terminal line, forged control lines, the stdout caps, and option injection.

## Out of scope

- Budget ledgers, version bumps, CHANGELOG steps, and vendor review bots from gstack.
- A shared run directory or journal. No skill needs resume today.
- A load-time preamble program. No skill here needs one today.
- CI jobs that call a model to block a merge. ADR-114 keeps agent verdicts advisory.

## Rollout

1. Land the ADR.
2. Audit every skill against R1 to R9. Record gaps and a priority per skill.
3. Pilot `ship` and `push-pr`.
   Their design draft sits unmerged on branch `refactor/ship-push-pr-pr-creation` (2026-11-25).
4. Land the deterministic evidence check. No second gated change merges first.
5. Each gated change lands through `ship` with its eval evidence in the PR body.

## Acceptance criteria

- [ ] The ADR is accepted after a full `adr-review` panel.
- [ ] The gap audit covers every template in `templates/skills/`.
- [ ] Each gated change shows `ACCEPTANCE GATE: PASS` with its command and scores.
- [ ] No driver runs a mutating command that a script owns.
