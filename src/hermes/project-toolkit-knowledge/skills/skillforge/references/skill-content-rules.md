# Skill content rules

Owner of the authoring and description rules for a `SKILL.md`. `skillforge`,
`skillify`, and `skillopt` cite this file instead of restating it. Read it
before you write, patch, or review a skill body or its `description`.

Source: the agentskills.io guides
<https://agentskills.io/skill-creation/best-practices> and
<https://agentskills.io/skill-creation/optimizing-descriptions>, plus the
specification at <https://agentskills.io/specification>.

## Content rules

Apply these to every section of the body.

- **Start from real expertise.** A draft written from model knowledge alone
  comes out generic ("handle errors appropriately"). Feed in project material:
  runbooks, API specs, schemas, code review comments, incident reports,
  version-control history, and real failure cases. Or finish a hands-on task
  first and extract the steps, corrections, and formats from it.
- **Keep only what changes behavior.** For each line, ask whether the agent
  would get this wrong without it. If not, cut it. If unsure, test it.
- **Size the scope as one coherent unit of work.** Too narrow forces several
  skills to load for one task. Too broad makes activation imprecise. Aim for
  moderate detail: concise steps and one working example beat exhaustive docs.
- **Stay under 500 lines and 5,000 tokens.** Move detail to `references/` and
  state when to load each file: "Read `references/api-errors.md` if the API
  returns a non-200 status", not "see references/". Give every reference row a
  load condition.
- **Use relative paths, one level deep.** Reference files by path relative to
  the skill root, and link them directly from `SKILL.md`. Do not chain
  references (a reference that points to another reference).
- **Keep gotchas in `SKILL.md`.** Gotchas (also called Pitfalls) are
  environment-specific facts that defy a reasonable assumption, such as a soft
  delete column or an endpoint that returns 200 while the database is down. The
  agent may not recognize the moment a reference file would apply, so they stay
  in the body where the agent reads them before it acts. Use one section, titled
  `## Gotchas` (or `## Pitfalls` in an existing skill). Do not keep both.
- **Match specificity to fragility.** Give exact commands where order or flags
  matter. Elsewhere state the goal and the reason, and leave the agent room.
- **Give one default per choice.** Name an alternative only with the condition
  that selects it. Do not list equal options.
- **Teach the method, not one answer.** Specific values are fine, but the
  approach must work on the next instance.
- **Show the output format as a template.** When format matters, put a concrete
  template inline (or in `assets/` if long). Agents pattern-match a template
  better than a prose description.
- **Track multi-step work with a checklist.** For a workflow with dependencies
  or gates, give the agent a progress checklist to copy and tick off.
- **Close the loop with validation.** Do the work, validate with a script or a
  reference checklist, fix, and repeat until it passes. For batch or destructive
  work, plan-validate-execute: write the plan to a file, check it against a
  source of truth, then run it.
- **Feed corrections back.** When a user corrects a run, add the correction to
  Gotchas. Read the execution trace as well as the output: wasted steps point
  to vague, inapplicable, or menu-style instructions.

## Description rules

The agent sees only `name` and `description` before it activates the skill, so
the description carries all of the triggering. The body loads after activation,
so a trigger phrase listed only in the body never routes.

- Say what the skill does and when to use it. Lead the second part with
  "Use when...", not "This skill does...".
- Describe what the user wants, not the skill's internal mechanics. Cover
  requests that never name the domain, and err toward listing adjacent cases
  where the skill applies. A bland description under-triggers.
- Name the boundary with the nearest adjacent skill ("Do NOT use for...").
- Stay under 1024 characters (a hard limit in the specification). Recheck the
  length after every edit.
- Quote a YAML value that contains a colon, or use a folded scalar (`>`). Many
  clients parse strictly, and an unquoted colon breaks the frontmatter.

To measure whether a description change helps, use `skillopt` and its
`references/description-optimization.md`.

For scripts bundled in a skill, read `references/script-design-rules.md`. It owns
the rules for prompts, `--help`, streams, exit codes, and `--dry-run`.
