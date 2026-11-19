# steering-matcher

Matches the files you are changing against the glob patterns in steering file front matter. It returns only the steering guidance that applies, sorted by priority, so an agent loads less context.

## When to use it

- The orchestrator needs to inject steering guidance based on the files a task touches.
- You want to scope agent guidance to relevant files to save tokens.
- Trigger phrases: `match steering for these files`, `which steering applies to this task`, `inject steering context`.

## When not to use it

- You already know which steering file applies: read the file directly.
- The task affects one known steering domain: read the file directly.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:steering-matcher`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the steering-matcher skill to find which steering applies to src/claude/security.md and .project-toolkit/security/SR-001-oauth-review.md.
```

The skill runs `get_applicable_steering.py` on those paths and returns the matching steering files.

## What you get

A JSON array. Each object has `name`, `path`, `apply_to`, and `priority`. The list is sorted with the highest priority first, and it has no duplicate entries.

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/steering-matcher/scripts/get_applicable_steering.py --help
uv run python .claude/skills/steering-matcher/scripts/get_applicable_steering.py --files src/claude/security.md --steering-path .agents/steering --json
```

Flags: `--files` (one or more paths), `--steering-path` (the steering directory), and `--json`.

The skill reads the `applyTo` glob patterns from each steering file's front matter. Process results in priority order, because lower-priority guidance can contradict higher. Do not hardcode steering paths or inject every steering file.

Chaining: [`context-gather`](context-gather.md) runs it as a sibling preflight skill in the build chain, and the [`orchestrator`](../agents/orchestrator.md) agent consumes the matches. The skill runs on the `haiku` model tier because the work is mechanical. From a repository checkout, `uv run pytest tests/skills/steering-matcher/ -q` runs its tests. Plugin installs do not ship them.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`context-gather`](context-gather.md): runs this skill as a preflight.
- [`orchestrator`](../agents/orchestrator.md): consumes steering matches.
- Source: [`SKILL.md`](../../src/claude/skills/steering-matcher/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
