---
name: build
description: Build incrementally. Implement changes in thin vertical slices with TDD and atomic commits. Run after /plan.
argument-hint: plan-step-or-task-description
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(*)
user-invocable: true
---

<!-- Copilot CLI: project instructions (CLAUDE.md) load via the plugin instructions tree; no include directive needed. -->
Build: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message) is empty, check for recent /plan output in the conversation. If none found, ask the user what to build.

## Cross-Harness Hook Routing

If the task touches Claude Code or GitHub Copilot CLI hook configuration,
payloads, decisions, matchers, exit codes, timeouts, generated shims, or event
translation:

1. Invoke `skill: "agent-harness-reference"` before design or code.
2. Execute the change through
   `skill: "ai-agents-portability-campaign"`.
3. Use `skill: "ai-agents-generation-and-release"` for generated mirrors.
4. Do not repeat vendor research unless the pinned source ledger is stale or
   the task explicitly requires a contract refresh.

## Complexity Assessment

Before implementation, `agent_type: "project-toolkit:analyst"`: Read `.claude/skills/analyze/references/engineering-complexity-tiers.md` and the task description. Classify as Tier 1-5. Return: tier, rationale, and recommended oversight level. Use this to calibrate implementation approach:

- Tier 1-2: Implement directly. Async code review sufficient.
- Tier 3: Validate approach before coding. Active mentorship pattern (check in at milestones).
- Tier 4-5: Proof-of-concept first. Get design sign-off before full implementation.

## Pre-Mortem (Risk Identification)

Before any code changes, invoke `skill: "pre-mortem"` on the task as briefed. Capture the top 2-3 critical risks and their mitigations in the active plan or issue handoff. Risks surfaced by reviewers late in the cycle are usually knowable up front. A 5-minute pre-mortem is cheaper than a 10-round bot review.

## Agent

`agent_type: "project-toolkit:implementer"`: You are a senior engineer. Discover the project's tech stack, coding patterns, and test conventions by reading the codebase. Build in thin vertical slices. Test-first when the project has tests. Commit atomically.

For each slice:

1. Read the spec AC for this slice. Every test must trace to an AC number from `/spec` output. Name the test `test_<behavior>` and include the AC identifier in the docstring or comment.
2. Understand the existing code patterns (read related files, check test conventions). If Serena is available, prefer it for symbolic search (canonical tool names: `mcp__serena__find_symbol`, `mcp__serena__get_symbols_overview`; some Claude harnesses surface the same tools under the plugin alias `mcp__plugin_serena_serena__find_symbol` / `mcp__plugin_serena_serena__get_symbols_overview`, so accept either when present). Otherwise fall back to `Grep` and `Read` for filesystem-level discovery. Serena is not guaranteed in every harness (fresh installs without MCP, copilot-cli runtime); the fallback keeps the slice executable across hosts.
3. **Write the failing test first.** This project has pytest 8+. TDD is unconditional. Never write code before a failing test exists. The test expresses the AC contract; code exists only to make it pass. Tests written after code confirm the code's behavior, not the spec's contract.
4. Write the minimum code to pass the test. Run the test, confirm it fails on the right assertion, then write code.
5. Refactor toward quality (cohesion, encapsulation, simplicity). Re-run the test.
6. **Self-apply gate for detection tools.** If this slice adds a guard, warning, or detector (hook, linter, threshold check), run it against the current branch NOW before committing. If it does not fire on conditions present in the branch, the threshold or detection logic is wrong. Fix the logic before step 7.
7. Commit with a conventional message. Each commit is one logical change. Test file and implementation file committed together.

## Quality Signals

The agent should self-check:

- Is this hard to test? That indicates a design problem, not a test problem.
- Does every method read like a sentence? (Programming by Intention)
- Is coupling intentional or accidental?
- Would a stranger understand this code without asking questions?

## Mandatory Exit Gates

The build is not complete until all four gates below return clean. These are **hard preconditions for declaring done**, not advisory output. If any gate returns findings, the implementer must address them in the same `/build` cycle. Do not kick the can to PR review; advisory framing here produces the iteration paradox where reviewers flag what the implementer should have caught, multiplying the cost of every revision.

Run, in order:

1. `skill: "code-qualities-assessment"` with `--changed-only --base origin/main --gate-mode regression` against the changed files. Reject the build if any changed method regresses below the configured thresholds in `.qualityrc.json`, or if a new method fails the absolute gate.
2. `skill: "taste-lints"` against the changed files (use `--git-staged` or pass paths explicitly). Reject the build on any error-level violation; address every warning surfaced on lines you touched.
3. `skill: "doc-accuracy"` with `--diff-base main` so it audits changed comments, docstrings, and prose. Reject the build on any critical or high finding in code or docs you authored.
4. `skill: "orphan-ref-validator"`. Reject the build on `VERDICT: CRITICAL_FAIL` or `VERDICT: ERROR`. Catches references to deleted skills and missing script paths before they reach review. Manifest count claims are not validated by anything: the marketplace count validator was retired in #2187 and orphan-ref-validator never took the work over. Its scanner emits only skill_name, script_path, and scan_truncated findings. To diagnose a failure, re-run the skill with `--output human`; each finding shows `path:line` plus a one-line recommendation. The skill invocation is platform-agnostic; each platform mirror runs its own copy of `scan.py`. The first three gates run in `--changed-only` mode and ignore preexisting drift; gate 4 scans the default targets across the repo because skill-name and script-path orphans are repo-state global, not per-PR. If pre-existing drift outside the PR's scope blocks the gate, fix it in the same PR (the directives at `<!-- orphan-ref-ignore -->` and `<!-- orphan-ref-ignore-file -->` are documented in the skill's SKILL.md).

If a gate flags an item that is genuinely out of scope for this build, document the rationale in the PR body or issue handoff and link to the follow-up issue. "I will fix it in review" is not an acceptable rationale.

## Guardrails

- Atomic commits. Each commit is one logical change, rollback-safe.
- No code without understanding the existing patterns first. Read memory via Serena when available; fall back to filesystem `Grep`/`Read` if Serena is not present. Read canonical source before writing code that touches it.
- Before modifying an existing system (changing behavior of a validator, hook, ADR constraint,
  or shared infrastructure component), invoke `skill: "memory-gate"` to surface the "why"
  behind the existing design. This is a soft BLOCKING check: if the gate returns findings, address
  or explicitly acknowledge them in the active plan or issue handoff before proceeding.
- Favor delegation over inheritance. A makes B, or A uses B. Never both.
- Three similar lines beat a premature abstraction.
- Verify CLI flags and argparse patterns against live output before committing. Run the command, observe the actual behavior, confirm it matches intent.
- Use the real repo as the integration test bed. Run new scripts against an open or recent PR before declaring done. Synthetic fixtures can only validate the wrapper; real data validates the semantic.
