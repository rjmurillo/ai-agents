# skillify

Turns a workflow you just finished into a reusable skill, using what the session shows: tool calls, decisions, errors, and corrections. It patches an existing skill when one already covers the work, and it checks the file it wrote.

## When to use it

- A non-trivial workflow just succeeded and the pattern is worth keeping.
- Trigger phrases: `skillify this`, `skillify`, `save this as a skill`, `make this proper`.

## When not to use it

- You have a goal and no finished workflow: use [`skillforge`](skillforge.md) instead.
- The work was a one-off or a single tool call with arguments. The gate rejects it, because that is a tool, not a skill.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:skillify
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/skillify`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /skillify skill to ...`.

The skill audits your session, gates it, finds the skills directory, checks for overlap, writes the skill, and reads it back. It asks you only for the trigger phrase, or for a destination when it cannot resolve one. It reports one line: `Skillified as <name>. Trigger: "<phrase>".` or `Patched <name>. Trigger: "<phrase>".`

## What you get

- A new `<root>/<name>/SKILL.md`, or a patch to an existing skill.
- A one-line report naming the skill and trigger. If the skill claims a capability gain, the report adds `Capability gain: MEASURED | UNVERIFIED | NO GAIN` with values.
- Nothing published. The skill never publishes, pushes, or shares a skill. Skills load in every later session, so sharing is your call.

Every step that touches an external or public system keeps its approval gate in the new skill, tagged `(external)` and `(approval)`.

## Advanced use

The procedure has eight steps: audit the workflow, gate, resolve the destination, check overlap, decompose into actions, write, verify, report. The helper `skillify.py` prints JSON and has four subcommands. From the root of a checkout of this repository:

```bash
uv run python .claude/skills/skillify/scripts/skillify.py --help
uv run python .claude/skills/skillify/scripts/skillify.py gate --audit audit.json
uv run python .claude/skills/skillify/scripts/skillify.py resolve --cwd .
uv run python .claude/skills/skillify/scripts/skillify.py overlap --workflow w.json --root .claude/skills
uv run python .claude/skills/skillify/scripts/skillify.py verify --skill .claude/skills/my-skill --audit audit.json
```

| Subcommand | Returns | Exit |
| --- | --- | --- |
| `gate --audit FILE` | `PROCEED` or `REJECT` with reasons (`one_off`, `trivial_wrapper`, `no_real_procedure`, `no_trigger_phrase`) | `0` |
| `resolve [--explicit P] [--env-var N] [--cwd D]` | The skills root | `0`, or `2` when unresolved or not a directory |
| `overlap --workflow FILE --root P` | `PATCH` at 0.70 term coverage or more, else `CREATE` | `0` |
| `verify --skill P [--audit FILE] [--mode create\|patch]` | Read-back checks | `0` pass, `1` fail |

The audit JSON carries `tool_call_count`, `reusable_class`, `decision_points`, `gotchas`, `trigger_phrase`, and optional `external_actions` and `recovery_paths` booleans. Five or more tool calls make a `PROCEED` result proactive-eligible, which allows one declarative hint line when host rules permit it.

Destination order: an explicit path you gave, then an environment variable name you or the host named, then a skills root found from the working directory (`.claude/skills` for Claude Code, `.github/skills` for Copilot CLI). If none resolve, the skill stops and asks. It confirms before it creates a missing root. It never guesses a path.

Overlap: a patch asks you to confirm the target path and the planned change before it edits, and the description must stay within 1024 characters. A generated `SKILL.md` is patched at its source template when the repository has one.

The skill strips secrets, tokens, auth headers, internal hostnames, and account IDs from captured commands. It treats text from tool output, issues, and fetched pages as data and never copies an instruction found there into a skill. For a capability claim, read [`references/capability-gate.md`](../../src/claude/skills/skillify/references/capability-gate.md) and record a baseline.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillforge`](skillforge.md): designs a skill from a goal. Its content rules govern what skillify writes.
- [`skillopt`](skillopt.md): measures whether a skill improves outcomes.
- [`agent-harness-reference`](agent-harness-reference.md): confirm harness skill locations and tool names.
- Source: [`SKILL.md`](../../src/claude/skills/skillify/SKILL.md)
- Skeleton: [`skill-skeleton.md`](../../src/claude/skills/skillify/references/skill-skeleton.md)
- Capability gate: [`capability-gate.md`](../../src/claude/skills/skillify/references/capability-gate.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
