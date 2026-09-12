# Claude model behavioral patches

Migrated from the retired `.claude/rules/claude-model-patches.md` (epic #5456,
milestone M4). `review` is not template-owned under ADR-108 (`SKILL.md` sits
139 bytes under the 24,576 byte ceiling, no room for the inline partial), so
this reference carries the same text instead of a rendered `{{> claude-model-patches}}` include.

This directory is not `references/`. `/review` discovers its canonical axis
set by globbing `references/*.md` (`select_axes.py`), so a non-axis document
placed there would enroll a phantom axis. This file lives in `resources/`
alongside `axis-selection.md` for the same reason.

These nudges are tuned for the Claude model family (Anthropic models) and bind
whenever Claude is the runtime model, regardless of harness. They are
subordinate to this skill's own workflow steps, STOP points, and exit gates:
when a patch below conflicts with one of those, the skill wins.

## Todo-list Discipline

When working through a multi-step plan, mark each task complete individually
as you finish it. Do not batch-complete at the end. If a task turns out to be
unnecessary, mark it skipped with a one-line reason.

Reason: a batched complete-everything-at-the-end pattern hides progress from
the user and from any orchestrator watching the run. If the model crashes or
the session ends mid-run, the todo list still reflects reality up to the last
completed step. Batched updates make every recovery start from zero.

Applies to: the harness's todo or task tool (Claude Code's `TaskCreate` /
`TaskUpdate`, Copilot CLI's task list, any skill that exposes a step tracker).

**Parallel tasks.** Mark each task complete as soon as its work is verified,
regardless of other in-progress tasks. Do not wait for siblings to finish.

## Think Before Heavy Actions

For complex operations, state your approach in 2 to 3 sentences before
executing. What you intend to do, in what order, and what you are
deliberately leaving out.

What counts as a "heavy action":

- A refactor that touches 4 or more files.
- A migration (schema, format, API version, dependency major bump).
- A new feature that touches more than one file OR more than one logical
  component.
- Anything that changes a public contract (signature, exported type, wire
  format, configuration shape).
- Anything irreversible without significant cleanup (delete, rewrite,
  force-push, schema drop).

The cost of a two-sentence preamble is roughly zero. The cost of a 30-minute
rollback is everything. The user course-corrects cheaply when the plan is
visible up front; not when the diff is already on disk.

**When a heavy action fails midway.** Mark the in-flight task as failed with
a one-line reason. If partial changes are reversible (uncommitted edits,
unpushed commits), revert them. If not (pushed commits, mutated external
state), state what was changed and what was not. Ask the user before
retrying; do not retry blindly.

## Dedicated Tools Over Bash

Prefer Read, Edit, Write, Glob, Grep over their shell equivalents (`cat`,
`sed`, `find`, `grep`).

Why:

- **Cheaper.** The dedicated tools have lower context impact. Bash pipes
  paste full outputs into the conversation; the dedicated tools surface only
  what they actually need.
- **Clearer.** The tool name announces the intent. A reviewer scanning the
  transcript can read "Edit auth.ts" faster than parsing
  `sed -i 's/foo/bar/g' auth.ts`.
- **Safer.** No shell quoting traps. No command-injection surface. No
  accidental glob expansion against paths the model did not intend.

Reserve Bash for operations the dedicated tools cannot perform: `git`,
package managers (`npm`, `pip`, `uv`, `cargo`), build runners (`make`,
`uv run python build/scripts/build_all.py`), anything that needs a real
shell environment or a multi-stage pipe.

**When a dedicated tool is unavailable in the current harness.** Fall back to
the closest Bash equivalent and state the fallback in your response so the
user knows the tool boundary was crossed.

Specific anti-patterns to reject:

- `cat <file>` to read for analysis. Use Read.
- `grep <pattern>` for symbol or text search. Use Grep.
- `find . -name <pattern>` for file location. Use Glob.
- `sed -i` to mutate a file. Use Edit.
- Heredocs to create a new file. Use Write.

Allowed Bash patterns:

- `git status`, `git log`, `git diff`, `git add`, `git commit`, `git push`.
- `gh <subcommand>` for GitHub API operations the harness does not expose.
- `python3 build/scripts/<name>.py` and other repo-specific runners.
- `mkdir`, `rm`, `mv` for directory operations.
- One-shot diagnostics (`uname`, `which`, `ls -la <specific path>`) when a
  dedicated tool does not cover it.

## Quick Self-Check

Run this check only at decision points: starting a heavy action, switching
tasks, or about to call Bash. Not every turn; the per-turn overhead would
compete with throughput.

- If this is one step in a multi-step plan, is the previous step's todo
  already marked complete?
- If this action is heavy (per the list above), did I state the approach?
- If I am about to call Bash, is there a dedicated tool that would do this
  better?

If any answer is "no" or "not sure," adjust before proceeding.

<!-- vendor-portability: declared. `build/scripts/build_all.py` and `build/scripts/<name>.py` above are example Bash-allowed runners describing what the upstream checkout permits, not a runtime instruction a vendored install resolves; `build/` ships in neither plugin root. Migrated from the retired `.claude/rules/claude-model-patches.md` (epic #5456). Issue #2050. -->
