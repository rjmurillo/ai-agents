# work-operating-model

Interviews you in five layers to find out how a team really works: rhythms, decisions, dependencies, institutional knowledge, and friction. You get a structured operating model as JSON that other agents can read.

## When to use it

- You need a baseline of team practice before an ADR, a retrospective, or a scope decision.
- You want to tailor an agent or skill to a team's real cadences and decision rights.
- Planning keeps stalling because nobody has the context on how the team operates.
- You say `elicit operating model`, `interview team operating model`, `how does this team actually work`, `resume operating model interview`, or `validate operating model`.

## When not to use it

- Questions about code, not people and process: use the [`analyst`](../agents/analyst.md) agent instead.
- A strategic narrative for an outside audience: use the [`explainer`](../agents/explainer.md) agent instead.
- A look back at a bounded past period: use the [`retrospective`](../agents/retrospective.md) agent instead.
- Mapping where automated judgment is safe: use [`world-model-diagnostic`](world-model-diagnostic.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:work-operating-model`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the work-operating-model skill to interview me about how the platform team works, and write the result to operating-model.json.
```

The skill confirms scope (team name, what the team owns, size), then asks one layer at a time. After each layer it summarizes back and asks you to confirm. At the end it writes the JSON and validates it.

## What you get

The JSON file is `<workspace>/operating-model.json`. You choose the workspace. The JSON is canonical. The skill can also write `USER.md`, `SOUL.md`, and `HEARTBEAT.md` as readable views derived from it.

| # | Layer | Question | Output section |
| --- | --- | --- | --- |
| 1 | Rhythms | When does work happen, and on what cadence? | `rhythms` |
| 2 | Decisions | Who decides what, and how is it recorded? | `decisions` |
| 3 | Dependencies | Who do you wait on, and who waits on you? | `dependencies` |
| 4 | Institutional knowledge | What lives in someone's head and not in a doc? | `institutional_knowledge` |
| 5 | Friction | What is broken or slow that the team has accepted? | `friction` |

Every item is tagged `documented` (with a link) or `tacit` (with the source person). A disagreement between sources is recorded as a finding, not an error.

## Advanced use

### Minimum valid document

- `schema_version`: `"1.0.0"`
- `team`: an object with `name`
- `rhythms`, `decisions`, `dependencies`, `institutional_knowledge`, `friction`: each an object (may be empty if the layer was skipped)
- `metadata`: an object with `interview_date` (`YYYY-MM-DD`), `interview_status` (`in_progress` or `complete`), and `completed_layers` (a list)

Skip a layer only when the team cannot answer it, and record the gap in `metadata.skipped_layers` with a reason.

### Validate

Run the validator from the root of a checkout of this repository:

```bash
uv run python .claude/skills/work-operating-model/scripts/validate_operating_model.py operating-model.json
```

It takes a path (use `-` to read stdin). The flag `--skip-path-validation` skips the path containment check and is for tests only.

| Exit code | Meaning |
| --- | --- |
| `0` | The document conforms to the schema |
| `1` | The document breaks the schema or is not valid JSON |
| `2` | Bad arguments or unreadable input |

### Resume an interview

Say `resume operating model interview`. The skill reads the existing JSON and builds the set of resolved layers from `metadata.completed_layers` plus the `layer` property of each entry in `metadata.skipped_layers`. It continues from the first layer, in table order, that is not in that set. It never re-asks a skipped layer. If every layer is resolved, it sets `metadata.interview_status` to `complete`.

The skill does not silently rewrite an earlier layer. To change an answer, it opens the discussion, updates the section, and appends to `metadata.revisions`.

Operating models drift. Re-validate quarterly and update `metadata.interview_date`.

Downstream agents that read the output include [`architect`](../agents/architect.md), [`roadmap`](../agents/roadmap.md), and [`orchestrator`](../agents/orchestrator.md). The [`spec`](spec.md) lifecycle skill uses it in Step 1 for a Tier 5 PRD.

Reference files: [`layer-questions.md`](../../src/claude/skills/work-operating-model/references/layer-questions.md) lists the prompts per layer. [`entry-contract.md`](../../src/claude/skills/work-operating-model/references/entry-contract.md) holds the full JSON schema.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`world-model-diagnostic`](world-model-diagnostic.md): maps where automated judgment is safe.
- [`analyst`](../agents/analyst.md): code and repo investigation.
- [`retrospective`](../agents/retrospective.md): bounded past periods.
- [`spec`](spec.md): calls this skill for Tier 5 PRD context.
- Source: [`SKILL.md`](../../src/claude/skills/work-operating-model/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
