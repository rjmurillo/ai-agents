# chestertons-fence

Investigates why existing code, a constraint, or an ADR exists before you change or remove it. It gathers git history, related PRs and ADRs, and dependents, then recommends a decision.

## When to use it

- You plan to change or delete a code pattern, architectural decision, ADR, constraint, or protocol rule.
- You plan to change a workflow configuration, CI pipeline, skill, hook, or agent prompt.
- You ask "why does this code or constraint exist" or "is it safe to remove this".
- Trigger phrases: `why does this exist`, `chestertons fence`, `before removing`, `investigate history`, `prior art investigation`.

## When not to use it

- You want forward-risk analysis of a plan: use [`pre-mortem`](pre-mortem.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:chestertons-fence "src/validators/schema.py" "remove unused validation"
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/chestertons-fence "src/validators/schema.py" "remove unused validation"`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /chestertons-fence skill to ...`.

The first argument is the target. The second describes the change you plan. The skill returns an investigation report with a recommended decision.

## What you get

| Input | Output | Destination |
| --- | --- | --- |
| File path or ADR number | Investigation report | `.project-toolkit/analysis/NNN-chestertons-fence-TOPIC.md` |
| Component description | Historical context summary | stdout (JSON) |

The report ends in one of four decisions:

| Decision | Use when |
| --- | --- |
| `PRESERVE` | The original rationale still applies. |
| `MODIFY` | The purpose is valid but the implementation needs updating. |
| `REPLACE` | A better approach exists and the original concern is addressed. |
| `REMOVE` | The original rationale no longer applies, with evidence. |

## Advanced use

The process has six steps: identify the structure, run git archaeology (`git log --follow` for a file, `git log -S` for a text span such as a section or rule line, for the origin commit, author, and date), confirm the origin with a second probe and `git show` (at most three rounds, then report every candidate), search for the originating PR and related ADRs, analyze dependencies, fill the report template, and decide. The skill reads ADRs from `${AWESOME_AI_ARCHITECTURE_DIR:-.project-toolkit/architecture}`. When that directory is absent in a vendored install, the search returns nothing.

Run the script directly from the root of a checkout of this repository:

```bash
uv run python .claude/skills/chestertons-fence/scripts/investigate.py --target src/validators/schema.py --change "remove unused validation" --format json
```

| Flag | Meaning |
| --- | --- |
| `--target` | File path, ADR number, or component to investigate. Required. |
| `--change` | Description of the proposed change. Required. |
| `--format` | `text` (default) or `json`. |

The script exits 0 when it prints the report. It exits 1 when the target path contains `..` or the target is not readable text.

For code committed in 2023 or later, the skill applies stricter evidence rules:

- Git history proves who committed the code and when. It does not prove intent.
- Author identity, complexity, polish, and apparent effort do not raise the odds that the code should stay.
- A missing rationale after steps 1 through 4 is itself evidence. Inconclusive evidence may lead to a yell-test proposal instead of `REMOVE`. The [`review`](review.md) skill owns the shape of that proposal. This skill supplies the evidence.

Agents use the report as follows:

| Agent | Use |
| --- | --- |
| [`analyst`](../agents/analyst.md) | Run this first when investigating changes. The report is a prerequisite for any change proposal. |
| [`architect`](../agents/architect.md) | ADRs that deprecate or replace a pattern include a "Prior Art Investigation" section. Generate it here. |
| [`implementer`](../agents/implementer.md) | Before deletions or major refactors, verify a report exists. If not, route to the analyst. |
| [`critic`](../agents/critic.md) | When a plan removes or replaces an existing system, check for investigation evidence. |

Anti-patterns to avoid:

| Avoid | Why | Instead |
| --- | --- | --- |
| Removing code you do not understand | May break hidden invariants | Investigate first, then decide |
| Assuming dead code is unused | Hyrum's Law: someone depends on it | Run dependency analysis |
| Skipping PR/ADR search | Loses original design rationale | Always check git history and PRs |
| Proposing replacement without evidence | Cannot compare tradeoffs | Document original constraints first |

[`memory-gate`](memory-gate.md) points here for the full four-phase investigation.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pre-mortem`](pre-mortem.md): forward-risk analysis, the complement of this backward look.
- [`memory-gate`](memory-gate.md): invokes this skill for the full investigation.
- [`review`](review.md): consumes the code-intent evidence this skill gathers.
- Source: [`SKILL.md`](../../src/claude/skills/chestertons-fence/SKILL.md)
- Reference: [`references/chestertons-fence-mental-model.md`](../../src/claude/skills/chestertons-fence/references/chestertons-fence-mental-model.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
