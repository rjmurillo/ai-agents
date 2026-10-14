---
name: skillify
version: 1.0.0
description: Extract a reusable skill from a workflow you just finished. Use when you say `skillify this`, `save this as a skill`, or `make this proper`. Do NOT use to design a skill from a goal (use skillforge).
license: MIT
user-invocable: true
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - skill-extraction-from-completed-workflow
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes a request to save a just-completed workflow as a skill
    user-facing: true
    intents:
      - skillify this
      - skillify
      - save this as a skill
      - make this proper
---

# Skillify

> Turn a workflow you just completed into a skill, from what the session
> shows, not from a goal. Patch an existing skill before creating a new one.

When a non-trivial workflow succeeds, the durable pattern is worth keeping.
This skill audits the finished work, decides if it deserves a skill, finds the
destination, checks for overlap, writes through the harness file tools, and
reads the result back.

Boundary with `skillforge`: skillify extracts from a workflow already done and
is driven by session evidence (tool calls, branches, errors). `skillforge`
routes, designs, creates, or improves skills from a goal with no finished
workflow behind it. Starting from a goal: use `skillforge`.

## Triggers

`skillify this`, `skillify`, `save this as a skill`, `make this proper`

Proactive hint: after a task that met the threshold below, the final report
may carry one declarative line naming the candidate and the phrase to run. It
is never a question, never an offer, and never a write. Omit it when the host
or the user restricts the report to the requested result.

## Contract

- A skill is written only when the Phase 0 gate returns `PROCEED`.
- Nothing is written until the destination resolves. Unresolved means stop and
  ask; never guess a path.
- An existing skill covering at least 70 percent of the workflow is patched,
  not duplicated.
- The written file is read back and passes `verify`; the report names the skill
  and its trigger.
- Approval gates for external or public actions and optional recovery paths
  survive into the generated skill. Skillify never publishes, pushes, or
  shares a skill itself.

## Procedure

### Process

All commands run
`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skillify/scripts/skillify.py`
with `python3`. Each prints one JSON object. Exit codes: `0` ok, `1` logic or
verification failure, `2` no destination. Harness tool names:
[harness-mapping.md](references/harness-mapping.md).

1. **Audit the workflow.** Write the audit from session evidence: what was
   done, tools used, decisions and what triggered each, errors and fixes,
   surprises, the trigger phrase the user used or would use. Count tool calls,
   decision points, gotchas, and note whether any action touches an external
   or public system.
2. **Gate.** Save the audit as JSON with `tool_call_count`, `reusable_class`,
   `decision_points`, `gotchas`, `trigger_phrase`, and optional
   `external_actions`, then run `skillify.py gate --audit audit.json`.
   `REJECT` lists reasons (`one_off`, `trivial_wrapper`, `no_real_procedure`,
   `no_trigger_phrase`). On `REJECT`, say the work did not warrant a skill and
   stop. A single tool call with arguments is a tool, not a skill.
3. **Resolve the destination before any path is written.** Answer four
   questions once: where the skill is installed, where it is invoked from,
   where it reads, where it writes. Then run
   `skillify.py resolve [--explicit PATH] [--env-var NAME ...]`. Order:
   explicit instruction, then the named env var, then a skills root found from
   the working directory (`.claude/skills` for Claude Code, `.github/skills`
   for Copilot CLI). Exit `2` with `needs_clarification` means stop all
   writes and ask the user for a path. Details:
   [skill-skeleton.md](references/skill-skeleton.md).
4. **Check for overlap.** Save the workflow as JSON (`actions`, `terms`,
   `trigger_phrase`) and run `skillify.py overlap --workflow w.json --root
   <resolved root> [--root <other root>]`. Add the user-scope root when the
   host has one. `PATCH` names the skill: read it and add the branch or pitfall
   with the harness edit tool. `CREATE` continues. When in doubt, patch.
5. **Decompose into actions.** For each action record: input, action and the
   concrete branch rule, output evidence that proves it ran, and state
   boundary (read-only, internal change, or external/public). Stop splitting
   when an action runs on its own and its result can be checked. Keep
   mandatory actions apart from optional recovery paths. Keep approval and
   draft gates exactly where the workflow had them.
6. **Write.** Use the skeleton in [skill-skeleton.md](references/skill-skeleton.md).
   Create `<root>/<name>/SKILL.md` with the harness file-write tool, or patch
   with the file-edit tool using a unique old string. Inline every convention
   the skill needs; do not depend on a personal instruction file or a path
   outside the skill. Use `pathlib` in any script and no assumed shell.
7. **Verify.** Run `skillify.py verify --skill <dir> --trigger "<phrase>"`
   (add `--external-actions` when step 1 found any). Fix every failure and
   rerun. Do not run a broader evaluation pass.
8. **Report in one line:** `Skillified as <name>. Trigger: "<phrase>".` or
   `Patched <name>. Trigger: "<phrase>".` No offers to adjust.

## Scripts

| Command | Purpose | Exit |
|---------|---------|------|
| `gate --audit FILE` | `PROCEED` or `REJECT` with reasons; `-` reads stdin | 0 |
| `resolve [--explicit P] [--env-var N]... [--cwd D]` | Pick the skills root | 0, or 2 unresolved or not a directory |
| `overlap --workflow FILE --root P...` | `PATCH` at 0.70 coverage else `CREATE` | 0 |
| `verify --skill P --trigger T [--external-actions]` | Read-back checks | 0 pass, 1 fail |

Malformed or unreadable input exits `1` with `status: error`.

## Anti-patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skillifying a one-off task | A script or note is the right size | Let the gate `REJECT` and stop |
| Creating a near-duplicate | Overlapping triggers rot the catalog | Run `overlap` first; patch at 0.70 |
| Writing a path before Phase 3 resolves | A wrong guess creates files in the wrong place | Resolve first; ask when unresolved |
| Vague description | Agents scan only the opening clause | Lead with the action and the real trigger phrase |
| Trigger phrases nobody says | The skill never loads | Use the user's own words |
| Dropping Anti-patterns and Pitfalls | Without them the skill is a README | Write at least two of each |
| Removing an approval gate while simplifying | A public action then runs unreviewed | Carry every gate into the new skill |
| Publishing the new skill automatically | Skills load in every later session | Write locally; leave sharing to the user |
| Asking about every section | Skillify is your work | Ask at most one thing: the trigger phrase |

## Pitfalls

- **Unique edit anchor.** A patch fails when the old string appears twice.
  Include the heading above the block and the line after it.
- **Names.** Kebab-case, at most 64 characters, equal to the directory name.
  Underscores and capitals are rejected by `verify`.
- **Skills are global.** A user-scope skill loads in every session. Keep
  user-specific names and paths out of a generic-looking skill, or say who it
  is for in the description.
- **Discovery surface.** The first 200 description characters carry the
  trigger phrase. Background goes in the body.
- **Hardcoded destinations.** One real skill shipped four revisions because it
  baked in a personal notes path, then an env var that assumed one tool's
  layout, before settling on a per-call order. Answer the I/O questions once.
- **Harness differences.** Claude Code loads `.claude/skills`; Copilot CLI
  loads `.github/skills`. Confirm with the `agent-harness-reference` skill
  before naming other locations or tool names.
- **Windows.** Pass paths as arguments, quote ones with spaces, and use
  `pathlib` in generated scripts.

## Verification

- [ ] The gate returned `PROCEED`, or the run stopped with the rejection reason.
- [ ] The destination came from explicit, env var, or cwd detection; an
      unresolved one produced no write.
- [ ] `overlap` ran; a skill at 0.70 or more was patched, not duplicated.
- [ ] `verify` returned `PASS` on the written file.
- [ ] External or public actions in the workflow kept their approval gates.
- [ ] The report is one line naming the skill and its trigger.
