---
name: pr-quality-devops
version: 1.0.0
description: Evaluate a local diff for CI/CD, build pipeline, and infrastructure risk, and return a PASS/WARN/CRITICAL_FAIL verdict. Use when you say `devops review my changes`, `run the devops gate`, or `is this workflow change safe`. Do NOT use to run all six axes (use pr-quality-all), and do NOT use to author the pipeline itself (use the devops agent).
license: MIT
allowed-tools: Bash(git:*), Read, Grep, Glob, serena/*
argument-hint: base-branch
user-invocable: true
---

# PR Quality Gate: DevOps

<!-- vendor-portability: contributor-facing pre-push gate for the rjmurillo/ai-agents
     repo itself. It intentionally reads .github/prompts/pr-quality-gate-devops.md
     (the same criteria CI runs) and emits against
     .agents/schemas/pr-quality-gate-output.schema.json; both live upstream only,
     so this skill's audience is repo contributors, not plugin consumers
     (ADR-083, issue #5632). -->

Run the devops axis of the quality gate against your working changes, before you
push, using the same criteria CI will apply.

Migrated from the pr-quality/devops command under ADR-064, which makes skills the
single user-invocable surface and renames the namespaced sub-command
pr-quality/devops to pr-quality-devops. The command file is gone, so its path is named
here in plain text rather than as a citation to something a reader could open.

## Triggers

`devops review my changes`, `run the devops gate`, `is this workflow change safe`, `pr-quality devops`

## Arguments

Base branch: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If `$ARGUMENTS` names a branch, diff against it. Otherwise default to `main`.

## Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-devops.md

That file is the canonical axis definition and the same one CI loads. Do not
paraphrase it from memory: read it, then judge the diff against what it says.

## Process

1. Run `git branch --show-current` to name the current branch.
2. Resolve the base branch from `$ARGUMENTS`, defaulting to `main`.
3. Run `git diff "<base_branch>" --name-only` to list the changed files.
4. Run `git diff "<base_branch>"` to read the full diff.
5. Judge the diff against every criterion in the axis file. Findings are
   additive: a criterion that fails does not end the pass, because the author
   needs the whole list in one round rather than one finding per round.
6. Emit the verdict block, then the JSON block.

## What this axis looks for

This axis reads the diff for an Action pinned to a floating tag, logic embedded in workflow YAML, a path filter on a whole-tree check, a step that swallows a failure into a green exit, and a secret reachable from a fork.

That list orients the read. The axis file is authoritative when the two differ.

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```

Then emit a fenced JSON block conforming to `.agents/schemas/pr-quality-gate-output.schema.json` with `"agent": "devops"`.

## Verification

- [ ] The axis file was read this run, not recalled
- [ ] The diff was taken against the resolved base branch, not against `HEAD~1`
- [ ] Every criterion in the axis file was judged, including the ones that passed
- [ ] Each finding names a file and a line, not a general concern
- [ ] The verdict block is the first thing emitted, with no preamble
- [ ] The JSON block validates against the schema and carries `"agent": "devops"`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Stopping at the first CRITICAL_FAIL | Findings are additive, so an early stop hides the rest and buys the author a second round | Record the verdict and keep judging the remaining criteria |
| Judging from memory of the axis | The criteria change and the recalled version is the one that was true once | Read `@.github/prompts/pr-quality-gate-devops.md` every run |
| A finding with no file and line | The author cannot act on it, so it reads as an opinion and gets skipped | Cite `path:line` and quote the offending span |
| A preamble before the verdict | The block is parsed by `pr-quality-all` and by CI, so leading prose breaks the merge | Emit `VERDICT:` first, every time |
| PASS on a diff you could not read | An unread diff is an unmeasured one, and PASS says the opposite | Emit CRITICAL_FAIL or UNKNOWN and name what blocked the read |

## Extension Points

- **New criterion.** Add it to `.github/prompts/pr-quality-gate-devops.md`, which
  CI and this skill both read, so the two cannot drift.
- **Different base.** Step 2 resolves the base from `$ARGUMENTS`; a project that
  merges into something other than `main` changes that default alone.
- **Another consumer.** The JSON block is schema-bound, so a new reader parses it
  without this skill changing.
