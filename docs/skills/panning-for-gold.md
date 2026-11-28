# panning-for-gold

Turns a raw voice transcript or brain dump into a ranked inventory of threads and a synthesized `gold-found` file. You get the ideas worth a deeper look, each one rated and wired to existing work.

## When to use it

- You have a voice transcript, stream-of-consciousness note, or brain dump with many ideas mixed with noise.
- You need a repeatable procedure to decide which ideas merit deeper analysis.
- You want a permanent, structured file that the [`analyst`](../agents/analyst.md) agent or the [`spec-generator`](spec-generator.md) skill can use.
- You want to mine agent session history for measured results that contradicted a memory, ADR, skill, or doc.
- You say `pan for gold`, `triage transcript`, `synthesize gold-found`, or `mine eureka moments`.

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

### Session corpus mode

Say `mine eureka moments` to run the same phases over agent session history. A eureka is a measured result that contradicted a memory, ADR, skill, doc, or common guidance.

The skill analyzes; it does not read session stores. A producer writes a JSONL corpus, described in [`corpus-format.md`](../../src/claude/skills/panning-for-gold/references/corpus-format.md). The [`skill-doctor`](skill-doctor.md) skill's `--export-corpus` flag is one producer. Any tool that writes the format works, so the mode runs where skill-doctor is not installed.

| Step | What happens |
| --- | --- |
| Feed | Get a corpus file. Bounded `grep` and `sed` only; never read a whole transcript. |
| Extract | `pan.py prefilter` drops injected text, keeps windows with a surprise signal and a number, removes duplicates, and writes batches. |
| Evaluate | Judge each batch. Verify each candidate with a transcript proof line and a check of the contradicted artifact on current main. |
| Synthesize | Write each kept finding as a decision memory through the memory-gate skill's contradiction log. Where that skill is not installed, such as Hermes, list each KEEP finding in the gold-found file. |

Artifacts still wrong on main become issue candidates in the `gold-found` file. Filing an issue or opening a pull request is a separate step that needs your approval for each item. The procedures are in [`contradiction-lens.md`](../../src/claude/skills/panning-for-gold/references/contradiction-lens.md). Inventory threads take four optional lens fields: `Claim`, `Conventional view`, `Evidence`, and `Strength`.

The workspace holds transcript-derived text. The repository `.gitignore` excludes `.panning/`. Keep corpus files out of version control too.

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
| `prefilter` | `--corpus`, `--lens`, `--out`, `--max-batch-chars` | Cut a session corpus into judge batches. `--out` must not already hold batch files, and `--corpus` must not be a `batch-*.jsonl` or `manifest.json` file inside `--out`. Output files are owner-only (mode 0600). |

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

`pan.py` calls `inventory.py` to parse and merge inventories, `synthesis.py` to generate the `gold-found` file, and `prefilter.py` to batch a session corpus. To change the workspace root, use `--workspace` or set the `PANNING_WORKSPACE` environment variable.

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
- Corpus contract: [`corpus-format.md`](../../src/claude/skills/panning-for-gold/references/corpus-format.md)
- Contradiction lens: [`contradiction-lens.md`](../../src/claude/skills/panning-for-gold/references/contradiction-lens.md)
- Template: [Gold-found template](../../src/claude/skills/panning-for-gold/references/gold-found-template.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
