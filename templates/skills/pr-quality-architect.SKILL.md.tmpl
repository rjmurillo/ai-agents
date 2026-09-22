---
name: pr-quality-architect
version: 1.0.0
description: Review a local diff for design patterns, system boundaries, coupling and cohesion, and ADR compliance, and return a PASS/WARN/CRITICAL_FAIL verdict. Use when you say `architect review my changes`, `run the architect gate`, or `does this respect our boundaries`. Do NOT use to run all six axes (use pr-quality-all), and do NOT use to author a new ADR (use architect).
license: MIT
allowed-tools: Bash(git:*), Read, Grep, Glob, mcp__serena__*
argument-hint: base-branch
user-invocable: true
---

# PR Quality Gate: Architect

<!-- vendor-portability: contributor-facing pre-push gate for the rjmurillo/ai-agents
     repo itself. It intentionally reads .github/prompts/pr-quality-gate-architect.md
     (the same criteria CI runs) and emits against
     .agents/schemas/pr-quality-gate-output.schema.json; both live upstream only,
     so this skill's audience is repo contributors, not plugin consumers
     (ADR-083, issue #5632). -->

Run the architect axis of the quality gate against your working changes, before you
push, using the same criteria CI will apply.

Migrated from the pr-quality/architect command under ADR-064, which makes skills the
single user-invocable surface and renames the namespaced sub-command
pr-quality/architect to pr-quality-architect. The command file is gone, so its path is named
here in plain text rather than as a citation to something a reader could open.

## Triggers

`architect review my changes`, `run the architect gate`, `does this respect our boundaries`, `pr-quality architect`

## Arguments

Base branch: $ARGUMENTS

If `$ARGUMENTS` names a branch, diff against it. Otherwise default to `main`.

## Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-architect.md

That file is the canonical axis definition and the same one CI loads. Do not
paraphrase it from memory: read it, then judge the diff against what it says.

## Process

1. Run `git branch --show-current` to name the current branch.
2. Resolve the base branch from `$ARGUMENTS`, defaulting to `main`. Reject an
   empty value or one starting with `-` (Git parses a leading dash as an
   option, not a ref), then resolve it to a commit with
   `BASE_SHA=$(git rev-parse --verify --quiet "<base_branch>^{commit}")`. An
   unresolved or rejected ref is a hard stop: report it and do not fall back
   to an empty diff. Use `$BASE_SHA` in every git command below, not the
   branch name: the branch can move between this step and a later diff, and
   the SHA cannot.
3. Build the changed-file list from tracked changes
   (`git diff "$BASE_SHA" --name-only`) plus untracked files
   (`git ls-files --others --exclude-standard`); the local review scope is
   uncommitted changes, and a tracked-only diff misses a change set that is
   entirely new files. Read each untracked file's full content directly, since
   it carries no diff against the base.
4. Run `git diff "$BASE_SHA"` to read the full diff of tracked changes.
5. Judge the diff against every criterion in the axis file. Findings are
   additive: a criterion that fails does not end the pass, because the author
   needs the whole list in one round rather than one finding per round.
6. Emit the verdict block, then the JSON block.

## What this axis looks for

This axis reads the diff for a boundary crossed without an interface, an accepted ADR contradicted, use mixed with creation, a module reaching into another's internals, and an abstraction added before a second caller exists.

That list orients the read. The axis file is authoritative when the two differ.

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```

Then emit a fenced JSON block conforming to `.project-toolkit/schemas/pr-quality-gate-output.schema.json` with `"agent": "architect"`.

## Verification

- [ ] The axis file was read this run, not recalled
- [ ] The diff was taken against `$BASE_SHA`, not the base branch name or `HEAD~1`
- [ ] The base ref was rejected if empty or leading-dash, and resolved to `$BASE_SHA` before any `git diff`
- [ ] Untracked files were included in the changed-file list, not only the tracked diff
- [ ] Every criterion in the axis file was judged, including the ones that passed
- [ ] Each finding names a file and a line, not a general concern
- [ ] The verdict block is the first thing emitted, with no preamble
- [ ] The JSON block validates against the schema and carries `"agent": "architect"`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Stopping at the first CRITICAL_FAIL | Findings are additive, so an early stop hides the rest and buys the author a second round | Record the verdict and keep judging the remaining criteria |
| Judging from memory of the axis | The criteria change and the recalled version is the one that was true once | Read `@.github/prompts/pr-quality-gate-architect.md` every run |
| A finding with no file and line | The author cannot act on it, so it reads as an opinion and gets skipped | Cite `path:line` and quote the offending span |
| A preamble before the verdict | The block is parsed by `pr-quality-all` and by CI, so leading prose breaks the merge | Emit `VERDICT:` first, every time |
| PASS on a diff you could not read | An unread diff is an unmeasured one, and PASS says the opposite | Emit CRITICAL_FAIL and name what blocked the read |

## Extension Points

- **New criterion.** Add it to `.github/prompts/pr-quality-gate-architect.md`, which
  CI and this skill both read, so the two cannot drift.
- **Different base.** Step 2 resolves the base from `$ARGUMENTS`; a project that
  merges into something other than `main` changes that default alone.
- **Another consumer.** The JSON block is schema-bound, so a new reader parses it
  without this skill changing.
