# Choose the right skill tool

## Goal

Pick the right one of five skills for the job in front of you. By the end you can name the skill and the phrase that starts it.

The five skills are `skillforge`, `skillify`, `skillopt`, `skill-bootstrap`, and `skill-doctor`. They overlap in name and not in job. Each skill's description ends with a "Do NOT use" line, and that line is the source for the table below.

## Before you start

- A checkout of this repository, or an install of the `project-toolkit` plugin. See [installation](../../installation.md).
- A rough idea of your starting point: a goal, a finished piece of work, a skill that misbehaves, a whole project, or a worry about your setup.

## Steps

1. Find your starting point in the table. Read across to the skill.

   | You have | Use | Start it with | Do not use it for |
   |----------|-----|---------------|-------------------|
   | A goal. You want a new skill, or want to know if one exists. | [`skillforge`](../../../.claude/skills/skillforge/SKILL.md) | `create a skill`, `do I have a skill for`, `improve the X skill` | Scored tuning (`skillopt`). Saving finished work (`skillify`). Placement or markdown compression (`context-optimizer`). |
   | A workflow you just finished and want to keep. | [`skillify`](../../../.claude/skills/skillify/SKILL.md) | `skillify this`, `save this as a skill` | Designing a skill from a goal (`skillforge`). |
   | A skill, agent file, or prompt that must get measurably better. | [`skillopt`](../../../.claude/skills/skillopt/SKILL.md) | `optimize this skill`, `make this skill better` | Creating or routing skills (`skillforge`). Compressing markdown with no eval (`context-optimizer`). |
   | A whole project with unwritten workflow knowledge. | [`skill-bootstrap`](../../../.claude/skills/skill-bootstrap/SKILL.md) | `bootstrap skills`, `build this repo's skill library` | One skill (`skillforge`). Scored tuning (`skillopt`). Session diagnosis (`skill-doctor`). |
   | A question about how your setup performs. | [`skill-doctor`](../../../.claude/skills/skill-doctor/SKILL.md) | `diagnose skill usage`, `grade my agent setup` | Creating skills (`skill-bootstrap`). Tuning (`skillopt`). |

2. Check the common mix-ups.
   - "I did the work and now want a skill" is `skillify`, not `skillforge`. `skillify` reads what the session did. `skillforge` starts from what you want.
   - "This skill is weak" is `skillopt` only if you have scored tasks. Without them, use `skillforge` to rewrite it. `skillopt` refuses to run with no scored eval set.
   - "My skills never fire" is `skill-doctor`. It reads your past sessions and shows which skills ran.
   - "Where do my skills belong, and should this be a skill at all?" is `context-optimizer`. None of the five answer it.

3. Know how they chain. `skill-bootstrap` calls `skill-doctor` to diagnose, `skillforge` to author, and `skillopt` to tune. You can also run them in this order by hand:
   `skillify` or `skillforge` to write the skill, `skillopt` to improve it, `skill-doctor` to see whether it gets used.

4. Use the short guide for your pick.

   **`skillforge`.** Say `SkillForge: {goal}` with the goal in plain words. It first checks whether a skill already covers the goal, so you do not get a duplicate. Depth scales with risk: a small edit stays light, and an ambiguous or consequential one gets a panel. Validate the result with the scripts in the "Validation and Packaging" section of its [SKILL.md](../../../.claude/skills/skillforge/SKILL.md). For the fields a skill needs, read [SKILL-AUTHORING.md](../../SKILL-AUTHORING.md).

   **`skill-bootstrap`.** Say `bootstrap skills`. It runs in one of two modes. `workflow` writes a skill only where it finds verified friction, such as repeated corrections or long review rounds. `knowledge` writes a skill only when a model without it gets a frozen test case wrong. There is no quota, so a run can write nothing. It asks at most five questions. Read [skill-bootstrap's SKILL.md](../../../.claude/skills/skill-bootstrap/SKILL.md) before you start, because it needs `skillforge` and `context-optimizer` installed.

   **`skill-doctor`.** Say `grade my agent setup`. It reads your local agent conversations and shows how your skills perform in one HTML report. Collection and rendering run on your machine. The conversation sources are Claude Code, Codex, Copilot CLI, Warp, Pi, Grok Build, ZCode, Hermes, and Factory Droid. For Factory Droid it reads `~/.factory/sessions`, and `--factory-home` points it at another location. The full table lives in [supported-harnesses.md](../../../.claude/skills/skill-doctor/references/supported-harnesses.md). If your harness is not listed, `skill-doctor` stops before it reads anything.

   **`skillify` and `skillopt`.** Do the walk-through in [Capture a workflow and tune it](capture-and-tune.md).

## Check your result

You are done when you can fill in this sentence: "I will run `<skill>` by saying `<phrase>`, because I have `<starting point>`."

To confirm the skills exist in your install, list them:

```bash
ls .claude/skills | grep -E '^(skillforge|skillify|skillopt|skill-bootstrap|skill-doctor)$'
```

Expected output, five lines:

```text
skill-bootstrap
skill-doctor
skillforge
skillify
skillopt
```

## If it does not work

- Fewer than five lines print. Your install is older than the skills, or you are on another harness. Copilot CLI keeps skills in `.github/skills`, so run the same `ls` there.
- A skill does not start when you say its phrase. Name it directly (`/skillopt` in Claude Code). Then read the "Skill Not Triggering" section of [SKILL-AUTHORING.md](../../SKILL-AUTHORING.md).
- You cannot tell which skill fits. Say what you want to `/autoplan`. It routes requests that name no skill.

## Next

- [Capture a workflow and tune it](capture-and-tune.md): a hands-on walk through `skillify` and `skillopt`.
- [SKILL-AUTHORING.md](../../SKILL-AUTHORING.md): frontmatter, validation rules, and the authoring checklist.
- [skill-reference.md](../../skill-reference.md): the catalog of skills.
