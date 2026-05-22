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
