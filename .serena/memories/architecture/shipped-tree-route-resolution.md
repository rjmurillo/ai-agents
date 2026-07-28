# Shipped trees must resolve their own routes

A routing table inside a shipped tree may only name skills that same tree
ships. Checking that the shipped copy matches its canonical source is a
different question and will not catch a violation.

## The incident

Issue #2026 removed `merge-resolver` from the Copilot shipping set. The skill
is hard-wired to this repository (`gh`, `.agents/sessions`, `.serena`,
session-protocol scripts) and fails on first use in a consumer repo. The
exclusion lives in `templates/platforms/copilot-cli.yaml`:

```yaml
excludeFilenames: ["AGENTS.md", "CLAUDE.md", "merge-resolver"]
```

`autoplan` kept routing merge-conflict work to `Skill: merge-resolver`. A
consumer who installed project-toolkit and hit a conflict was sent to a route
their install does not contain. This survived from #2026 until #3716.

## Why no gate caught it

Two control planes, each internally consistent:

1. The packaging exclusion is correct. The skill is absent on purpose.
2. The routing table is byte-identical to `.claude/skills/autoplan/SKILL.md`,
   where the route is correct because that tree has the skill.

Generation-drift gates ask "does the shipped copy match its source". The answer
was yes. Nothing asked "do the shipped copy's references resolve in the shipped
tree". The defect lived between two correct checks, so tightening either one
would not have found it.

Same class as `.claude/rules/plugin-self-containment.md`: anything referenced
from inside a plugin root must be encapsulated there. That rule covers
frontmatter paths. This covers body routing tables.

## The fix pattern

When a skill is excluded from a platform on purpose, route to the agent
instead:

```markdown
| Merge conflicts | Task(subagent_type="merge-resolver") |
```

`build/scripts/copilot_body_translation.py` rewrites `subagent_type="X"` to
`` `agent_type: "project-toolkit:X"` `` generically. It resolves to
`.claude/agents/merge-resolver.md` on Claude and to the shipped
`merge-resolver.agent.md` on Copilot. Agents ship even when their skill does
not, so the capability survives the exclusion. No generator change is needed.
The autoplan table already used this form for its orchestrator row.

## The gate

`scripts/validation/check_shipped_skill_routes.py`. Registered in
`scripts/validation/checks_plugin.py` for the pre-push path and as a step in
`.github/workflows/validate-generated-agents.yml`. Runs in roughly 140ms.

It reports a `Skill: <name>` reference only when that name exists as a skill in
the canonical tree. That is deliberate. A bare regex false-positives on prose
such as a checklist line reading `Skill: create ...`, where `create` is an
English verb. Requiring canonical existence states the drift signature exactly:
canonical has it, shipped dropped it, a reference survives. An unknown name is
prose or a typo, a different defect class.

Not covered: routes expressed in other shapes, for example a bare markdown link
into a skill directory. `SHIPPED_TREES` lists `src/copilot-cli` only, and
nothing forces a third shipping tree to be added.

## When this matters

Before excluding anything from a platform shipping set, grep the shipped tree
for references to the excluded name. The exclusion and the references are
edited in different files, usually in different sessions, and every gate stays
green in between.
