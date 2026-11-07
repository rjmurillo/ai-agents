# Skill content rules

Owner of the authoring and description rules for a `SKILL.md`. `skillforge`,
`skillify`, and `skillopt` cite this file instead of restating it. Read it
before you write, patch, or review a skill body or its `description`.

Source: the agentskills.io best practices and description optimization guides.

## Content rules

Apply these to every section of the body.

- **Keep only what changes behavior.** For each line, ask whether the agent
  would get this wrong without it. If not, cut it. If unsure, test it.
- **Stay under 500 lines and 5,000 tokens.** Move detail to `references/` and
  state when to load each file: "Read `references/api-errors.md` if the API
  returns a non-200 status", not "see references/".
- **Keep gotchas in `SKILL.md`.** The agent may not recognize the moment a
  reference file would apply. Facts that defy a reasonable assumption belong in
  Pitfalls, not in a reference.
- **Match specificity to fragility.** Give exact commands where order or flags
  matter. Elsewhere state the goal and the reason, and leave the agent room.
- **Give one default per choice.** Name an alternative only with the condition
  that selects it. Do not list equal options.
- **Teach the method, not one answer.** Specific values are fine, but the
  approach must work on the next instance.
- **Feed corrections back.** When a user corrects a run, add the correction to
  Pitfalls. Read the execution trace as well as the output: wasted steps point
  to vague, inapplicable, or menu-style instructions.

## Description rules

The agent sees only `name` and `description` before it activates the skill, so
the description carries all of the triggering. The body loads after activation,
so a trigger phrase listed only in the body never routes.

- Say when to act: "Use when...", not "This skill does...".
- Describe what the user wants, not the skill's internal mechanics. Cover
  requests that never name the domain.
- Name the boundary with the nearest adjacent skill ("Do NOT use for...").
- Stay under 1024 characters. Recheck the length after every edit.

To measure whether a description change helps, use `skillopt` and its
`references/description-optimization.md`.

For scripts bundled in a skill, read `references/script-design-rules.md`. It owns
the rules for prompts, `--help`, streams, exit codes, and `--dry-run`.
