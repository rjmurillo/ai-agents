# retrospective

Turns a session or task into written learnings. It gathers evidence, runs Five Whys and fishbone diagnosis, scores each learning for atomicity, and writes a retrospective file.

## When to use it

- A `reflect` pass produced a high-confidence finding.
- `main` went red, or a merge was reverted or force-fixed.
- You corrected the work explicitly and want root-cause analysis.
- An unfilled auto-retro skeleton exists in `.project-toolkit/retrospective/`.
- Trigger phrases: `run a retrospective`, `retro fill`, `list pending retros`, `extract learnings from this session`, `diagnose this failure`, `what did we learn`.

## When not to use it

- You want to capture one correction mid-conversation: use [`reflect`](reflect.md).
- You want a quick save point with no analysis: use [`checkpoint`](checkpoint.md).
- A session ended and nothing above fired. A calendar is not a trigger.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:retrospective the CI outage on 2026-11-09
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/retrospective the CI outage on 2026-11-09`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /retrospective skill to ...`.

The argument is the scope. A bare `/retrospective` asks you for one. Use `list` to see pending skeletons, or `fill <YYYY-MM-DD>` to fill one.

## What you get

One Markdown file at `.project-toolkit/retrospective/YYYY-MM-DD-[scope].md`, matching the Learning Extraction Template. Each learning carries an atomicity score and an evidence reference. Learnings scoring at least 70 percent are persisted to Serena memory. If the memory write fails, the artifact notes it.

When you fill an auto-retro skeleton, the skill overwrites the placeholders in the existing `YYYY-MM-DD-auto-retro.md` and removes the UNFILLED banner. Nothing writes new skeletons, because the Stop hook that did was deleted. Existing ones are historical but still fillable.

The skill reads evidence and writes one artifact plus memory entries. It does not open PRs or file issues. Actionable items go in the artifact's `Findings for the owner` table, and the owner decides what becomes tracked work.

## Advanced use

The skill runs six phases in order:

| Phase | Purpose | Tools |
| --- | --- | --- |
| 0. Data gathering | Facts before interpretation. | `friction_report.py candidates` first (it lists failed calls that a later call got past), then 4-Step Debrief, Execution Trace, Outcome Classification (Mad, Sad, Glad). |
| 1. Generate insights | Find causes. | Five Whys (mandatory for every failure), Fishbone, Force Field, Patterns and Shifts, Learning Matrix. |
| 2. Diagnosis | Prioritize findings. | Root-cause pattern storage. `diagnose this failure` stops here. |
| 3. Decide | Move to action. | Action Classification (Keep, Drop, Add, Modify), SMART validation, dependency ordering. |
| 4. Learning extraction | Score and assemble. | Atomicity score 0 to 100 percent. Vague statements are rejected. |
| 5. Persist and close | Store and evaluate. | Memory write, +/Delta, ROTI, Helped, Hindered, Hypothesis. |

Evidence sources are the latest session log under `.project-toolkit/sessions/`, `git log` for the period, optional GitHub activity through the `github` skill, and an optional native Copilot journal. A missing source is marked absent. The skill never invents data.

Run the scripts from the root of a checkout of this repository:

```bash
uv run python .claude/skills/retrospective/scripts/run_retrospective.py --scope 2026-11-09 --since "1 day ago" --learning "Pin actions to a SHA"
uv run python .claude/skills/retrospective/scripts/extract_evidence.py --scope 2026-11-09 --journal "$HOME/.copilot/session-state/$SESSION_ID/events.jsonl"
uv run python .claude/skills/retrospective/scripts/score_atomicity.py "Run pre_pr.py before every push" --json
```

| Script | Flags | Exit codes |
| --- | --- | --- |
| `run_retrospective.py` | `--scope`, `--project-dir`, `--since`, `--learning` (repeatable), `--fill`, `--output` | 0 artifact written, 1 a learning scored below threshold (artifact still written), 2 usage or configuration error, 3 external failure |
| `extract_evidence.py` | `--scope`, `--project-dir`, `--since`, `--journal` | 0 evidence gathered, 2 bad project directory, 3 external failure |
| `score_atomicity.py` | `learning` (or stdin), `--json` | 0 at or above 70 percent, 1 below, 2 no learning given |

The `fill` and `list` argument handling is in [`references/skeleton-fill.md`](../../src/claude/skills/retrospective/references/skeleton-fill.md). The rubrics live in [`frameworks.md`](../../src/claude/skills/retrospective/references/frameworks.md) and [`diagnosis-and-actions.md`](../../src/claude/skills/retrospective/references/diagnosis-and-actions.md). The [`retrospective` agent](../agents/retrospective.md) loads these references.

For a large session log, distill it once with the [`context-optimizer`](context-optimizer.md) skill and search the raw source for any detail the digest lacks.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`retrospective` agent](../agents/retrospective.md): the agent that loads this skill's rubrics.
- [`reflect`](reflect.md): the mini version for in-conversation corrections.
- [`checkpoint`](checkpoint.md): redirects retrospective requests here.
- Source: [`SKILL.md`](../../src/claude/skills/retrospective/SKILL.md)
- Reference: [`learning-template.md`](../../src/claude/skills/retrospective/references/learning-template.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
