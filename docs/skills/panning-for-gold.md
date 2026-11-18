# panning-for-gold

Turns a raw voice transcript or brain dump into a ranked inventory of threads and a synthesized `gold-found` file. You get the ideas worth a deeper look, each one rated and wired to existing work.

## When to use it

- You have a voice transcript, stream-of-consciousness note, or brain dump with many ideas mixed with noise.
- You need a repeatable procedure to decide which ideas merit deeper analysis.
- You want a permanent, structured file that the [`analyst`](../agents/analyst.md) agent or the [`spec-generator`](spec-generator.md) skill can use.
- You say `pan for gold`, `triage transcript`, or `synthesize gold-found`.

## When not to use it

- The input is already structured, such as a spec, ADR, or code: use the [`analyst`](../agents/analyst.md) agent or the [`spec-generator`](spec-generator.md) skill instead.
- You only need a one-off summary: use a generic summarizer.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:panning-for-gold`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the panning-for-gold skill to triage .panning/transcripts/2026-standup-ramble.txt and produce a gold-found file.
```

The agent first answers six front-gate questions. If they pass, it extracts every thread, evaluates each one, and writes the `gold-found` file.

## What you get

A workspace folder, `./.panning/` by default, with this layout:

```text
<workspace>/
|-- transcripts/          # Raw input (read-only after capture)
|-- inventories/          # Pass1 + final inventories
|-- evaluations/          # Per-thread evaluation files
`-- gold-found/           # Synthesized gold-found files
```

The script creates missing subdirectories on demand. It never overwrites an existing file unless you pass `--force`.

The `gold-found` file has a metadata block, then High-Signal, Medium-Signal, and Low-Signal sections in that order. Every High-Signal thread carries a `Connects to:` line that names a skill, ADR, Serena memory, open issue, or prior session log.

## Advanced use

### The four phases

| Phase | Name | What happens |
| --- | --- | --- |
| 0 | Front-gate | Six forcing questions run before any script. Documentation-only, with no script enforcement. |
| 1 | Extract | Build a pass1 inventory with no filtering. Every thread is recorded. |
| 2 | Evaluate | Write one evaluation file per thread: supporting evidence, what would falsify it, and the action it implies. |
| 3 | Synthesize | Combine the final inventory and evaluations into the `gold-found` file. |

Each thread block holds a `Signal` (high, medium, or low), a verbatim `Quote`, a one-sentence `Context`, and a one-sentence `Initial take`.

### Front-gate questions

Phase 0 asks: Demand Reality, Status Quo, Desperate Specificity, Narrowest Wedge, Observation, and Future-fit. If Demand Reality is aspirational ("might be useful someday"), or you cannot name a downstream consumer, discard or archive the transcript unprocessed.

### Elaboration gate

For each High-Signal thread, write one `Connects to: <artifact name> (<one-line why>).` line. The skill searches skills, ADRs, Serena memories, open issues, and prior session logs. This gate is applied by the agent, not enforced by a script. If no connection exists, treat that as a flag: the thread may not be as strong as it looked, or the search was too shallow.

### Run the scripts directly

Run from the root of a checkout of this repository:

```bash
uv run python .claude/skills/panning-for-gold/scripts/pan.py --help
```

| Subcommand | Flags | Purpose |
| --- | --- | --- |
| `init` | `--workspace` | Create the workspace layout. Defaults to `./.panning`. |
| `validate` | `--inventory` | Validate an inventory file. |
| `merge` | `--pass1`, `--final`, `--output`, `--force` | Merge the pass1 and final inventories. |
| `synth` | `--inventory`, `--evaluations`, `--output`, `--source`, `--force` | Build the `gold-found` file. `--source` sets a label in the metadata block. |

Example:

```bash
uv run python .claude/skills/panning-for-gold/scripts/pan.py init --workspace .panning
uv run python .claude/skills/panning-for-gold/scripts/pan.py synth --inventory inventory.md --evaluations .panning/evaluations --output .panning/gold-found/result.md
```

| Exit code | Meaning |
| --- | --- |
| `0` | OK. |
| `1` | Logic error, such as a malformed inventory or evaluation. |
| `2` | Config error, such as bad usage or an I/O problem. |

`pan.py` calls `inventory.py` to parse and merge inventories, and `synthesis.py` to generate the `gold-found` file. To change the workspace root, use `--workspace` or set the `PANNING_WORKSPACE` environment variable.

### Chaining

The [`research`](research.md) skill checks the Phase 0 front-gate before it triages raw unstructured input. The `gold-found` file feeds the [`analyst`](../agents/analyst.md) agent and the [`spec-generator`](spec-generator.md) skill.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`research`](research.md): checks the Phase 0 front-gate before it triages raw input.
- [`spec-generator`](spec-generator.md): consumes the `gold-found` file for structured specs.
- [`analyst`](../agents/analyst.md): consumes the `gold-found` file for deeper analysis.
- Source: [`SKILL.md`](../../src/claude/skills/panning-for-gold/SKILL.md)
- Template: [Gold-found template](../../src/claude/skills/panning-for-gold/references/gold-found-template.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
