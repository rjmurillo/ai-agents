# Eight-run eval archive: unified-software-engineering

Raw result artifacts behind the headline table in
`.claude/skills/context-optimizer/references/rule-audit-procedure.md`. They are
committed because the analysis in that document and in
`model-context-doctrine.md` cannot be checked without them, and the originals
were written to `/tmp`.

## Provenance

The artifacts record only a `rules` key, so everything below was recorded by
hand. Issue #3956 tracks storing it in the artifact.

| Field | Value |
|---|---|
| Date | 2026-07-29 |
| Rule under test | `unified-software-engineering` |
| Scenarios | 3 positive, 1 negative |
| Provider | `EVAL_PROVIDER=copilot-cli` |
| Requested models | `claude-opus-5` (`*opus*`), `gpt-5.6-sol` (`*sol*`) |
| Actual model served | not recorded |
| Judge samples per cell | 3, median reduced |
| Generations per cell | 1 |
| Ambient instructions | present; predates `--no-custom-instructions` |

Model attribution rests on the filenames. Nothing inside the files confirms
which model produced them.

## Reproducing the table

Failed judge samples store their truncated raw payload in `reasoning` behind a
`judge parse error: ` prefix. Strip the prefix, feed the remainder to
`_salvage_scores` in `scripts/eval/eval-rule-activation.py`, walk
`rules.<name>.scenarios[].mechanisms[]`, and re-median each cell over the
positive scenarios.

## What salvage did and did not contribute

Measured 2026-07-30 by walking all eight files, corrected 2026-07-30 after
round 10 review:

| Quantity | Count |
|---|---|
| Judge samples | 288 |
| `judge_failed` in the stored artifacts | 24 |
| Graded in the stored artifacts | 264 |
| Carrying a `judge_salvaged` marker | 0 |

**These files store the state before salvage was applied.** An earlier version
of this section read the zero marker count as proof that salvage never reached
a published cell, and concluded no change to the salvage path could move a
published number. That was wrong, and it was wrong in the direction of
comfort. The published table in `rule-audit-procedure.md` was recomputed with
all 24 recovered; the artifacts were not rewritten. The zero is an artifact of
when these files were serialized, not evidence about the table.

What salvage actually contributed, measured against the table:

- Re-running the current parser over the 24 stored payload prefixes recovers
  **all 24**: seventeen at 5/4/5, five at 5/5/5, one 2/2/1, one 2/3/1. The
  published table is reproducible from the code as it now stands.
- Recovery moved **exactly one published cell**: `fx-opus5` baseline, 3.83 to
  3.89. That changed the row's delta-full from +0.28 to +0.22.
- The sign count did not change. Seven positive deltas against one negative
  either way, so the conclusion does not rest on the recovery.

Two limits on what this archive can support:

- **It cannot say how many of the 264 graded samples reached a score through
  `_extract_json_object`'s prefix path** rather than a clean whole-payload
  parse, nor how many were unwrapped from a Markdown fence. Neither path was
  marked until rounds 9 and 10 added `judge_salvaged` to them. That gap is the
  reason the marker exists, and the reason no claim about tightening the
  parser can be validated here.
- **Re-walking the 24 failures is weaker than it looks.** Only 200 characters
  of each payload survive (#3975), so a re-parse exercises the stored prefix,
  not the payload the judge actually emitted. A duplicate score field in the
  discarded tail would refuse under the current guard and is invisible here.
  All 24 prefixes recover; that shows the hardening did not make the parser
  worse on what was kept, not that it matches on what was not.

A third figure that was published as free is not. Of the 264 graded samples,
none has a `reasoning` string naming a score field. That was read as evidence
that refusing any payload whose prose names a field costs nothing. It is
evidence about one judge, one prompt, and one provider, not about judge output
in general, and the guard has since been narrowed to count the JSON key shape
instead.

## Known limits

These runs carry the defects the procedure document lists. They are archived as
the evidence behind a specific conclusion, not as a clean dataset:

- Ambient user-level instructions were present in every cell.
- The Copilot provider injects treatment text into the user message, so this
  measures priming rather than always-on placement (issue #3934).
- The judge is the same model family being evaluated.
- Negative scenarios do not feed the verdict (issue #3933).
