# checkpoint

Writes a timestamped snapshot of your decisions, progress, and next actions, with secrets redacted. It links the snapshot from the active session log. It never commits or pushes.

## When to use it

- You want a recovery point before a risky change.
- You reached the end of a working block and want a durable record.
- Trigger phrases: `checkpoint this`, `save a recovery point`, `snapshot where we are`.

## When not to use it

- You want to commit or push: this skill does neither. Use [`push-pr`](push-pr.md) or [`ship`](ship.md).
- You want a retrospective: use [`retrospective`](retrospective.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:checkpoint before-schema-migration
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/checkpoint before-schema-migration`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /checkpoint skill to ...`.

The label is optional. The skill writes the checkpoint file, then reports the path and whether it linked the file from a session log.

## What you get

- A checkpoint file in the `checkpoints/` directory of your agent-artifacts tree. The skill resolves that directory the way `paths.artifact_dir` does and does not hard-code it.
- A timestamped, collision-safe path. The skill never overwrites an existing checkpoint.
- A body that passed through the secret redactor before the write.
- A metadata entry in the active JSON session log, when a branch-matching log exists. The skill validates the updated JSON before it edits the original file. If no log exists, it reports that reason and does not create one.

## Advanced use

| Invocation | Effect |
| --- | --- |
| `/checkpoint` | Write a timestamped checkpoint and link it from the active session log. |
| `/checkpoint <label>` | Write a labeled checkpoint and link it from the active session log. |

The work runs in three phases:

1. Build the checkpoint path: timestamp, active session log, label, slug, and a collision-safe path.
2. Build and redact the body. The redactor is [`scripts/redact_secrets.py`](../../scripts/redact_secrets.py) from the upstream `rjmurillo/ai-agents` repository. It ships in no plugin root, and the skill runs the body through it before any write.
3. Write the redacted file to a path that does not exist, append metadata to the session log, and validate the JSON.

Those phases expand into eight steps in [`references/steps.md`](../../src/claude/skills/checkpoint/references/steps.md). Read it before you change how the skill writes anything. The order of redaction and validate-before-edit is the part that matters.

If the redactor fails, the skill does not write unredacted text. When you later commit a checkpoint file, the commit message follows the repository convention.

To add restore or automatic checkpointing, build a separate skill. This one only writes and links snapshots on request.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`retrospective`](retrospective.md): the skill for retrospectives, which this one does not write.
- Source: [`SKILL.md`](../../src/claude/skills/checkpoint/SKILL.md)
- Reference: [`references/steps.md`](../../src/claude/skills/checkpoint/references/steps.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
