# A Copilot Skill Mirror Has Two Possible Canonical Sources

## The contradiction

Conventional reading of `src/copilot-cli/skills/<name>/SKILL.md`: skills are
single-source, so the canonical file is `.claude/skills/<name>/SKILL.md`. If that
directory is missing, the mirror is orphaned or was hand-edited, and either way it
is drift.

That inference is wrong for a whole class of skills. `src/copilot-cli/skills/` is
written by **two** generators, and only one of them reads `.claude/skills/`.

## The two pipelines

| Generator | Reads | Writes |
|---|---|---|
| `build/scripts/generate_skills.py` | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` |
| `build/scripts/generate_commands.py` | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` |

Copilot CLI plugins have no native custom slash-command surface. The command bridge
exists because a `user-invocable: true` skill fires as `/SKILL-NAME`, which is the
only way to give a Claude slash command a Copilot equivalent. So every
`.claude/commands/<name>.md` lands in the **skills** tree on the Copilot side.

`push-pr` is the worked example. `.claude/skills/push-pr/` does not exist and never
did. `.claude/commands/push-pr.md` is the canonical source, and
`src/copilot-cli/skills/push-pr/SKILL.md` is its generated mirror.

## Consequences

**Do not conclude drift from a missing `.claude/skills/<name>/`.** Check
`.claude/commands/<name>.md` before filing it as an orphan or a hand-edit.

**A PR body that names `.claude/skills/<name>/SKILL.md` for a bridged command names
a path that does not exist.** The PR-description gate reads that as a claim about the
diff and blocks the check.

**Editing a bridged skill means editing the command.** Changing
`src/copilot-cli/skills/<name>/SKILL.md` directly violates the canonical-source-mirror
rule and is reverted by the next generator run.

## The names cannot collide

`_detect_authored_skill_collision` in `generate_commands.py` aborts the build when
`.claude/skills/<name>/SKILL.md` exists for a name that is also a command, because
bridging would silently shadow the authored skill. The failure message asks a human
to rename one of the two.

So the source is unambiguous by construction: exactly one of
`.claude/skills/<name>/` and `.claude/commands/<name>.md` is the canonical source for
any given `src/copilot-cli/skills/<name>/SKILL.md`, and the build fails rather than
guess.

## Evidence

PR #4431's diff changed `src/copilot-cli/skills/push-pr/SKILL.md` without a matching
`.claude/skills/push-pr/` change, which reads as generated-artifact drift. It is not.
The PR body named a `.claude/skills/push-pr/SKILL.md` path that has never existed,
which is what the description gate flagged.

## Related

- [agents-two-pipeline-mirror-recipe](../agents-two-pipeline-mirror-recipe.md). The
  agent-side equivalent, where four surfaces are hand-maintained and two generated.
