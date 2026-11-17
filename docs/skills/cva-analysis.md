# cva-analysis

Finds natural abstractions with Commonality Variability Analysis (CVA). You build a matrix of what stays constant and what varies across your use cases, and design patterns emerge from the matrix instead of being picked first.

## When to use it

- You face two or more similar requirements and need to find the right abstraction.
- You are about to choose a design pattern and want evidence first.
- You are refactoring duplicated logic.
- Your team debates whether to abstract, and you need ADR material.
- You say `discover abstractions for {domain}`, `run CVA analysis`, `commonality variability analysis`, `prevent wrong abstraction`, or `what patterns emerge from {use cases}`.

## When not to use it

- Only one use case exists. Wait for a second.
- The pattern is obvious and nobody disputes it.
- You have under 15 minutes. Use judgment.
- Requirements are still highly uncertain.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:cva-analysis`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the cva-analysis skill to find the abstractions across our credit card, PayPal, and bank transfer payment flows.
```

The skill lists the commonalities, lists how each varies, builds a matrix, maps it to patterns, and hands off an ADR stub.

## What you get

| Phase | Output |
| --- | --- |
| 1. Identify commonalities | What every use case needs (matrix rows) |
| 2. Identify variabilities | How each commonality differs (matrix columns) |
| 3. Build matrix | A Markdown table, at least 2 by 2, with every cell filled |
| 4. Map to patterns | Pattern recommendations with rationale that cites the matrix |
| 5. Validate and hand off | A validation result, an ADR stub, and reassessment triggers |

How the matrix maps to patterns:

- Rows that differ across columns point to a Strategy.
- Columns that form coherent families point to an Abstract Factory.
- When two axes both vary, each axis gets its own first-class abstraction. Independent axes get one Strategy hierarchy each. Correlated axes point to Bridge. Sparse valid pairs point to Abstract Factory.

If no pattern fits, document why you keep a concrete implementation.

## Advanced use

Pick a depth by impact:

| Tier | Time | Use cases |
| --- | --- | --- |
| Quick | 15 min | 2 to 3 |
| Standard | 30 min | 3 to 5 |
| Deep | 60 min | 6 or more |

Validate a matrix file from the root of a checkout of this repository:

```bash
uv run python .claude/skills/cva-analysis/scripts/validate-cva-matrix.py cva-matrix.md --verbose
```

| Argument | Meaning |
| --- | --- |
| `matrix_file` | Path to the CVA matrix Markdown file. |
| `--verbose`, `-v` | Verbose output. |

| Exit code | Meaning |
| --- | --- |
| 0 | Valid matrix, patterns suggested |
| 1 | File not found or invalid format |
| 10 | Missing rows or columns, or empty cells |

If validation fails, go back to Phase 1 for missing commonalities, Phase 3 for an incomplete matrix, or Phase 4 for a pattern mismatch.

For handoff, ask [`decision-critic`](decision-critic.md) to validate the abstraction, and delegate to the `architect` agent to turn the ADR stub into a formal ADR. Use the `independent-thinker` agent when CVA is borderline and you doubt the abstraction is needed.

Re-run CVA when three or more new use cases arrive, when the architecture shifts, when the abstraction hurts performance, when the team says it is too complex, or at a quarterly review.

The source lists a template generator and a matrix exporter as planned. They do not exist yet, so build the matrix and any diagram by hand. [`review`](review.md) invokes this skill when a change introduces a new abstraction.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`decision-critic`](decision-critic.md): challenges the abstraction CVA recommends.
- [`architect`](../agents/architect.md): writes the formal ADR from the stub.
- [`independent-thinker`](../agents/independent-thinker.md): questions whether you need the abstraction.
- [`review`](review.md): calls this skill for new abstractions.
- Source: [`SKILL.md`](../../src/claude/skills/cva-analysis/SKILL.md)
- References: [`pattern-mapping-guide.md`](../../src/claude/skills/cva-analysis/references/pattern-mapping-guide.md), [`matrix-building-examples.md`](../../src/claude/skills/cva-analysis/references/matrix-building-examples.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
