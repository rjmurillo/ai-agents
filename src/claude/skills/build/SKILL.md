---
name: build
version: 1.0.0
description: Implement a planned change in thin vertical slices, test-first, with atomic commits and four mandatory exit gates. Use when you say `build this`, `implement this slice`, or `write the code for this task`, and run it after plan. Do NOT use to decide what to build (use spec) or to sequence the work (use plan), and do NOT use to review a finished diff (use review).
license: MIT
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(*)
argument-hint: plan-step-or-task-description
user-invocable: true
---

# Build

Implement in thin vertical slices, test-first, committing atomically, and do not
declare done until four gates return clean.

Migrated from `.claude/commands/build.md` under ADR-064, which makes skills the
single user-invocable surface.

## Triggers

`build this`, `implement this slice`, `write the code for this task`,
`start building`

## Arguments

ultrathink

Build: $ARGUMENTS

If `$ARGUMENTS` is empty, check for recent plan output in the conversation. If
none is found, ask what to build rather than inferring it.

## Cross-Harness Hook Routing

If the task touches Claude Code or GitHub Copilot CLI hook configuration,
payloads, decisions, matchers, exit codes, timeouts, generated shims, or event
translation:

1. Invoke `Skill(skill="agent-harness-reference")` before design or code.
2. Execute the change through
   `Skill(skill="ai-agents-portability-campaign")`.
3. Use `Skill(skill="ai-agents-generation-and-release")` for generated mirrors.
4. Do not repeat vendor research unless the pinned source ledger is stale or
   the task explicitly requires a contract refresh.

## Process

### Phase 1: Assess complexity

`Task(subagent_type="analyst")`: Read the engineering complexity tiers reference
in the `analyze` skill, resolved through
`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/analyze/references/engineering-complexity-tiers.md`,
and the task description. Classify as Tier 1-5. Return tier, rationale, and
recommended oversight level. Calibrate the implementation approach:

| Tier | Approach |
|------|----------|
| 1-2 | Implement directly. Async code review is sufficient. |
| 3 | Validate the approach before coding. Check in at milestones. |
| 4-5 | Proof of concept first. Get design sign-off before full implementation. |

### Phase 2: Pre-mortem

Before any code changes, invoke `Skill(skill="pre-mortem")` on the task as
briefed. Capture the top 2-3 critical risks and their mitigations in the active
plan or issue handoff. Risks surfaced by reviewers late in the cycle are usually
knowable up front. A five-minute pre-mortem is cheaper than a ten-round bot
review.

### Phase 3: Implement the slices

`Task(subagent_type="implementer")`: You are a senior engineer. Discover the
project's tech stack, coding patterns, and test conventions by reading the
codebase. Build in thin vertical slices. Test-first when the project has tests.
Commit atomically.

For each slice:

1. Read the spec AC for this slice. Every test must trace to an AC number from
   spec output. Name the test `test_<behavior>` and include the AC identifier in
   the docstring or comment.
2. Understand the existing code patterns (read related files, check test
   conventions). If Serena is available, prefer it for symbolic search (canonical
   tool names: `mcp__serena__find_symbol`, `mcp__serena__get_symbols_overview`;
   some Claude harnesses surface the same tools under the plugin alias
   `mcp__plugin_serena_serena__find_symbol` /
   `mcp__plugin_serena_serena__get_symbols_overview`, so accept either when
   present). Otherwise fall back to `Grep` and `Read` for filesystem-level
   discovery. Serena is not guaranteed in every harness (fresh installs without
   MCP, copilot-cli runtime); the fallback keeps the slice executable across
   hosts.
3. **Write the failing test first.** This project has pytest 8+. TDD is
   unconditional. Never write code before a failing test exists. The test
   expresses the AC contract; code exists only to make it pass. Tests written
   after code confirm the code's behavior, not the spec's contract.
4. Write the minimum code to pass the test. Run the test, confirm it fails on the
   right assertion, then write code.
5. Refactor toward quality (cohesion, encapsulation, simplicity). Re-run the test.
6. **Self-apply gate for detection tools.** If this slice adds a guard, warning,
   or detector (hook, linter, threshold check), run it against the current branch
   NOW before committing. If it does not fire on conditions present in the
   branch, the threshold or detection logic is wrong. Fix the logic before step 7.
7. Commit with a conventional message. Each commit is one logical change. Test
   file and implementation file committed together.

   Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.

## Quality Signals

The agent should self-check:

- Is this hard to test? That indicates a design problem, not a test problem.
- Does every method read like a sentence? (Programming by Intention)
- Is coupling intentional or accidental?
- Would a stranger understand this code without asking questions?

## Claude Model Behavioral Patches

These nudges are tuned for the Claude model family (Anthropic models) and bind whenever Claude is the runtime model, regardless of harness. They are subordinate to this skill's own workflow steps, STOP points, and exit gates: when a patch below conflicts with one of those, the skill wins.

### Todo-list Discipline

When working through a multi-step plan, mark each task complete individually as you finish it. Do not batch-complete at the end. If a task turns out to be unnecessary, mark it skipped with a one-line reason.

Reason: a batched complete-everything-at-the-end pattern hides progress from the user and from any orchestrator watching the run. If the model crashes or the session ends mid-run, the todo list still reflects reality up to the last completed step. Batched updates make every recovery start from zero.

Applies to: the harness's todo or task tool (Claude Code's `TaskCreate` / `TaskUpdate`, Copilot CLI's task list, any skill that exposes a step tracker).

**Parallel tasks.** Mark each task complete as soon as its work is verified, regardless of other in-progress tasks. Do not wait for siblings to finish.

### Think Before Heavy Actions

For complex operations, state your approach in 2 to 3 sentences before executing. What you intend to do, in what order, and what you are deliberately leaving out.

What counts as a "heavy action":

- A refactor that touches 4 or more files.
- A migration (schema, format, API version, dependency major bump).
- A new feature that touches more than one file OR more than one logical component.
- Anything that changes a public contract (signature, exported type, wire format, configuration shape).
- Anything irreversible without significant cleanup (delete, rewrite, force-push, schema drop).

The cost of a two-sentence preamble is roughly zero. The cost of a 30-minute rollback is everything. The user course-corrects cheaply when the plan is visible up front; not when the diff is already on disk.

**When a heavy action fails midway.** Mark the in-flight task as failed with a one-line reason. If partial changes are reversible (uncommitted edits, unpushed commits), revert them. If not (pushed commits, mutated external state), state what was changed and what was not. Ask the user before retrying; do not retry blindly.

### Dedicated Tools Over Bash

Prefer Read, Edit, Write, Glob, Grep over their shell equivalents (`cat`, `sed`, `find`, `grep`).

Why:

- **Cheaper.** The dedicated tools have lower context impact. Bash pipes paste full outputs into the conversation; the dedicated tools surface only what they actually need.
- **Clearer.** The tool name announces the intent. A reviewer scanning the transcript can read "Edit auth.ts" faster than parsing `sed -i 's/foo/bar/g' auth.ts`.
- **Safer.** No shell quoting traps. No command-injection surface. No accidental glob expansion against paths the model did not intend.

Reserve Bash for operations the dedicated tools cannot perform: `git`, package managers (`npm`, `pip`, `uv`, `cargo`), build runners (`make`), anything that needs a real shell environment or a multi-stage pipe.

**When a dedicated tool is unavailable in the current harness.** Fall back to the closest Bash equivalent and state the fallback in your response so the user knows the tool boundary was crossed.

Specific anti-patterns to reject:

- `cat <file>` to read for analysis. Use Read.
- `grep <pattern>` for symbol or text search. Use Grep.
- `find . -name <pattern>` for file location. Use Glob.
- `sed -i` to mutate a file. Use Edit.
- Heredocs to create a new file. Use Write.

Allowed Bash patterns:

- `git status`, `git log`, `git diff`, `git add`, `git commit`, `git push`.
- `gh <subcommand>` for GitHub API operations the harness does not expose.
- `mkdir`, `rm`, `mv` for directory operations.
- One-shot diagnostics (`uname`, `which`, `ls -la <specific path>`) when a dedicated tool does not cover it.

### Quick Self-Check

Run this check only at decision points: starting a heavy action, switching tasks, or about to call Bash. Not every turn; the per-turn overhead would compete with throughput.

- If this is one step in a multi-step plan, is the previous step's todo already marked complete?
- If this action is heavy (per the list above), did I state the approach?
- If I am about to call Bash, is there a dedicated tool that would do this better?

If any answer is "no" or "not sure," adjust before proceeding.

## Mandatory Exit Gates

> When every requested deliverable satisfies the frozen task contract and no blocker remains, the current task is terminal. Stop autonomous work.

The build is not complete until all four gates below return clean. These are
**hard preconditions for declaring done**, not advisory output. If any gate
returns findings, the implementer must address them in the same build cycle. Do
not kick the can to PR review; advisory framing here produces the iteration
paradox where reviewers flag what the implementer should have caught,
multiplying the cost of every revision.

Run, in order:

1. `Skill(skill="code-qualities-assessment")` with `--changed-only --base origin/main --gate-mode regression` against the changed files. Reject the build if any changed method regresses below the configured thresholds in `.qualityrc.json`, or if a new method fails the absolute gate.
2. `Skill(skill="taste-lints")` against the changed files (use `--git-staged` or pass paths explicitly). Reject the build on any error-level violation; address every warning surfaced on lines you touched.
3. `Skill(skill="doc-accuracy")` with `--diff-base main` so it audits changed comments, docstrings, and prose. Reject the build on any critical or high finding in code or docs you authored.
4. `Skill(skill="orphan-ref-validator")`. Reject the build on `VERDICT: CRITICAL_FAIL` or `VERDICT: ERROR`. Catches references to deleted skills and missing script paths before they reach review. Manifest count claims are not validated by anything: the marketplace count validator was retired in #2187 and orphan-ref-validator never took the work over. Its scanner emits only skill_name, script_path, and scan_truncated findings. To diagnose a failure, re-run the skill with `--output human`; each finding shows `path:line` plus a one-line recommendation. The first three gates run in `--changed-only` mode and ignore preexisting drift; gate 4 scans the default targets across the repo because skill-name and script-path orphans are repo-state global, not per-PR. If pre-existing drift outside the PR's scope blocks the gate, fix it in the same PR (the directives at `<!-- orphan-ref-ignore -->` and `<!-- orphan-ref-ignore-file -->` are documented in that skill's own SKILL.md).

If a gate flags an item that is genuinely out of scope for this build, document
the rationale in the PR body or issue handoff and link to the follow-up issue.
"I will fix it in review" is not an acceptable rationale.

## Verification

- [ ] Complexity tier assigned, and the oversight level matches the tier table
- [ ] Pre-mortem run, with its top risks recorded in the plan or handoff
- [ ] Every test traces to a named AC identifier
- [ ] Every test was seen failing on the right assertion before its code existed
- [ ] Any guard or detector added in this build was run against the branch and observed firing
- [ ] All four exit gates returned clean, or each finding has a documented out-of-scope rationale and a linked issue
- [ ] Commits are atomic, with test and implementation committed together

> After reporting a completed requested result, remove any unsolicited offer, question, or invitation whose only function is to continue the interaction.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Writing code before a failing test | A test written after the code confirms the code's behavior, not the spec's contract | Write the test, watch it fail on the right assertion, then implement |
| Treating the exit gates as advisory | Produces the iteration paradox: reviewers flag what the implementer should have caught, and every revision costs more | Clear all four in the same build cycle |
| Shipping a detector without self-applying it | A guard that does not fire on conditions already in the branch has wrong logic, and nobody finds out until it matters | Run it against the branch before committing |
| Coding before reading the surrounding patterns | Produces a second convention in a file that already had one | Read related files and test conventions first |
| Premature abstraction | Three similar lines are cheaper to read and to delete than a wrong shared helper | Wait for the third case |
| "I will fix it in review" | Moves work to the most expensive place to do it | Fix it now, or document the rationale and link the follow-up |

## Guardrails

- Atomic commits. Each commit is one logical change, rollback-safe.
- No code without understanding the existing patterns first. Read memory via Serena when available; fall back to filesystem `Grep`/`Read` if Serena is not present. Read canonical source before writing code that touches it.
- Before modifying an existing system (changing behavior of a validator, hook, ADR constraint,
  or shared infrastructure component), invoke `Skill(skill="memory-gate")` to surface the "why"
  behind the existing design. This is a soft BLOCKING check: if the gate returns findings, address
  or explicitly acknowledge them in the active plan or issue handoff before proceeding.
- Favor delegation over inheritance. A makes B, or A uses B. Never both.
- Three similar lines beat a premature abstraction.
- Verify CLI flags and argparse patterns against live output before committing. Run the command, observe the actual behavior, confirm it matches intent.
- Use the real repo as the integration test bed. Run new scripts against an open or recent PR before declaring done. Synthetic fixtures can only validate the wrapper; real data validates the semantic.

## Extension Points

- **New exit gate.** Add it to the numbered list and to the Verification
  checkbox that covers the gates, so it is both run and checked.
- **Different tier calibration.** Phase 1's table maps tier to oversight. A
  project with different risk tolerance changes that table alone.
- **Non-pytest stacks.** Phase 3 step 3 names pytest because this project uses
  it. The unconditional-TDD rule is stack-independent; swap the runner.
