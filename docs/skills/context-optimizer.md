# context-optimizer

Helps you decide where guidance belongs (a skill, always-on passive context, or both), then shrinks it. It classifies content, compresses markdown, splits a large file into an index plus detail files, digests big logs, and validates the result.

## When to use it

- You are deciding whether new guidance should be a skill or always-on context.
- You want to cut the token cost of a markdown file.
- You want to audit whether an always-on rule earns its slot.
- Trigger phrases: `analyze skill placement`, `compress markdown`, `optimize context`, `extract and index`, `audit always-on rules`.

## When not to use it

- You want to gather knowledge before a task: use [`context-gather`](context-gather.md) instead.
- You want to create or improve a skill: use [`skillforge`](skillforge.md) instead.
- You want a measured, eval-gated improvement of a skill: use [`skillopt`](skillopt.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:context-optimizer analyze skill placement for .claude/skills/github
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/context-optimizer`.

The skill runs the analyzer and returns a JSON classification: `Skill`, `PassiveContext`, or `Hybrid`, with a confidence and the reasoning.

## What you get

| Script | Output | Exit codes |
| --- | --- | --- |
| `analyze_skill_placement.py` | JSON with `classification`, `confidence`, `reasoning`, and `recommendations` | `0` success, `1` error |
| `compress_markdown_content.py` | Compressed markdown report (JSON on stdout by default) | `0` done, `1` input not found, `2` invalid level, `3` output write failed, `4` tiktoken not installed |
| `extract_and_index.py` | Detail files plus a compact pipe-delimited index | `0` success, `1` error, `2` config, `3` external, `4` tiktoken not installed |
| `distill_artifact.py` | A cached markdown digest of a log or diff with line citations; no model call | `0` success, `2` config, `3` external |
| `test_skill_passive_compliance.py` | Compliance report against the decision framework | `0` pass, `1` violations |

Classification thresholds: `Skill` when the skill score beats the passive score by 3 or more, `PassiveContext` when the passive score wins by 3 or more, and `Hybrid` when the gap is under 3.

## Advanced use

The first question is not "skill or passive context". It is: does the model already know this? Passive context earns its slot only for what the model cannot know: repository gotchas, local conventions that contradict the default, and APIs newer than the training cutoff. Generic engineering knowledge belongs in progressive disclosure or nowhere. Read `references/model-context-doctrine.md` before you argue about always-on content.

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/context-optimizer/scripts/analyze_skill_placement.py -p .claude/skills/github -d
uv run python .claude/skills/context-optimizer/scripts/compress_markdown_content.py -i README.md -l medium
uv run python .claude/skills/context-optimizer/scripts/extract_and_index.py -i AGENTS.md -d .agents-details -o AGENTS-INDEX.md
uv run python .claude/skills/context-optimizer/scripts/distill_artifact.py build.log --format json
uv run python .claude/skills/context-optimizer/scripts/test_skill_passive_compliance.py --path .claude --format table
```

Key flags:

- `analyze_skill_placement.py`: `-p/--path` (directory or `SKILL.md`), `-c/--content`, `-d/--detailed`.
- `compress_markdown_content.py`: `-i`, `-l light|medium|aggressive`, `-o`, `-v`.
- `distill_artifact.py`: `--out-dir`, `--max-matches`, `--edge-lines`, `--format path|json`. The digest keeps signal lines, the first and last lines, and per-file counts for a diff. Save the output to a file first, because a pipe loses the raw copy and the command's exit code.
- `test_skill_passive_compliance.py`: `--path`, `--claude-md-path`, `--format json|table`.

The analyzer reports shape, not admission. It cannot tell whether the model already knows the content. The compliance report is diagnostic, not a verdict: it lists what it does not evaluate, and each passive rule still needs an evidence-based keep or remove decision.

> [!NOTE]
> The `audit always-on rules` procedure needs a full checkout of `rjmurillo/ai-agents`. It runs that repository's eval harness and rule generator, which a plugin install does not include. The doctrine and instrument write-ups are readable anywhere.

Chaining: [`skillforge`](skillforge.md) points here for progressive disclosure guidance before you add always-on context. [`skill-bootstrap`](skill-bootstrap.md) runs this skill on each skill it authors.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillforge`](skillforge.md): creates and improves skills.
- [`skillopt`](skillopt.md): measured skill improvement.
- [`context-gather`](context-gather.md): collects knowledge before a task.
- Source: [`SKILL.md`](../../src/claude/skills/context-optimizer/SKILL.md)
- Doctrine: [`model-context-doctrine.md`](../../src/claude/skills/context-optimizer/references/model-context-doctrine.md)
- Audit procedure: [`rule-audit-procedure.md`](../../src/claude/skills/context-optimizer/references/rule-audit-procedure.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
