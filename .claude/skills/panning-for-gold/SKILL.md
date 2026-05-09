---
name: panning-for-gold
version: 1.0.0
model: claude-sonnet-4-6
description: "Triage raw unstructured input (transcripts, brain dumps) into evaluated thread inventories and a synthesized gold-found file across three phases."
license: MIT
---

# Panning for Gold

Turn raw, unstructured capture into an evaluated, actionable inventory of threads. Three phases: Extract, Evaluate, Synthesize.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `pan for gold` | Run the full extract -> evaluate -> synthesize procedure |
| `triage transcript` | Build inventory of threads from a raw transcript |
| `synthesize gold-found` | Generate the final gold-found file from evaluations |

## When to Use

Use this skill when:

- You have a voice transcript, stream-of-consciousness note, or brain dump that contains many ideas mixed with noise.
- You need a deterministic procedure to triage which ideas merit deeper analysis.
- You want a permanent, structured artifact that downstream agents (analyst, spec-generator) can consume.

Use a different skill when:

- The input is already structured (specs, ADRs, code). Use the analyst or spec-generator agents instead.
- You only need a one-off summary. Use a generic summarizer.

## Workspace Layout

The skill operates inside a workspace root. The default is `./.panning/` in the current working directory; override via `--workspace <path>` or the `PANNING_WORKSPACE` environment variable.

```text
<workspace>/
|-- transcripts/          # Raw input (read-only after capture)
|-- inventories/          # Pass1 + final inventories
|-- evaluations/          # Per-thread evaluation files
`-- gold-found/           # Synthesized gold-found files
```

The script creates missing subdirectories on demand. It never overwrites an existing file unless `--force` is passed.

## Process

### Phase 0: Front-gate (run before Extract)

Before triaging, run the six forcing questions against the input itself (see `front-gate-before-pipeline` skill if available; otherwise apply inline):

1. **Demand Reality** — Is anyone (including you) actually waiting on insight from this brain dump, or did you capture it because something was on your mind?
2. **Status Quo** — What happens if this transcript sits untriaged for another month? If "nothing breaks," that's a signal.
3. **Desperate Specificity** — Name the specific decision, person, or artifact that needs the gold-found output.
4. **Narrowest Wedge** — Could you extract one high-signal thread by hand in 10 minutes instead of running the full three-phase pipeline?
5. **Observation** — Have you re-read the transcript recently, or are you triaging from memory of why it felt important when captured?
6. **Future-fit** — If extraction produces nothing actionable, will you delete the gold-found file or let it accumulate?

**Halt criteria**: if Demand Reality is aspirational ("might be useful someday") or Desperate Specificity can't name a downstream consumer, the right move is to discard the transcript or archive it unprocessed. Triaging unmotivated capture produces gold-found files nobody reads.

### Phase 1: Extract

Build a pass1 inventory from a transcript without filtering. Every thread that surfaces is recorded.

Each thread block uses this structure:

```markdown
## Thread N: <short title>

- **Signal**: high | medium | low
- **Quote**: "<verbatim quote that surfaced this thread>"
- **Context**: <one sentence on where this came from>
- **Initial take**: <one sentence on why this might matter>
```

The pass1 inventory is provisional. A second pass refines and merges into a final inventory.

### Phase 2: Evaluate

For each thread in the final inventory, write an evaluation file. The evaluation captures depth: what evidence supports the thread, what would falsify it, what action it implies.

Evaluations are independent. They can be authored serially or in parallel.

### Phase 3: Synthesize

Combine the final inventory and the evaluation files into a gold-found markdown file. The gold-found file groups threads by signal level (High, Medium, Low) and includes a metadata block at the top.

**Elaboration gate (mandatory for High-signal threads)**: For each High-signal thread, force one explicit connection to an existing artifact — a skill, an ADR, a Serena memory, an open issue, a prior session log. Write the connection as a one-liner under the thread: `Connects to: <artifact name> (<one-line why>).`

If no connection exists, treat that as a flag, not a feature. Genuinely novel insights are rare; usually "no connection" means either (a) the thread isn't as high-signal as it looked, or (b) you haven't searched hard enough. Run a vault/skill/session search before promoting it. The forcing function catches false positives and produces compounding knowledge instead of orphan notes.

This is the elaboration principle (Make It Stick) applied at the synthesis layer: new findings are only durable knowledge once wired to existing entities. Standalone artifacts decay; connected ones compound.

## CLI

```text
pan.py init      --workspace <path>
pan.py validate  --inventory <file>
pan.py merge     --pass1 <file> --final <file> --output <file>
pan.py synth     --inventory <file> --evaluations <dir> --output <file>
```

The script delegates to `inventory.py` for parsing and merging, and `synthesis.py` for gold-found generation.

## Acceptance Checklist

- [ ] Inventory thread blocks contain `Signal`, `Quote`, `Context`, `Initial take` fields.
- [ ] Final inventory deduplicates threads from pass1 by title.
- [ ] Gold-found file has a metadata block plus High-Signal, Medium-Signal, and Low-Signal sections in that order.
- [ ] No threads from the inventory are silently dropped.

## References

- `references/inventory-template.md` - thread inventory skeleton.
- `references/gold-found-template.md` - gold-found skeleton.
