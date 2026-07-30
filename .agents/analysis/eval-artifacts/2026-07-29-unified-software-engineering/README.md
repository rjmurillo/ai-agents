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

Measured 2026-07-30 by walking all eight files:

| Quantity | Count |
|---|---|
| Judge samples | 288 |
| Graded, fed the medians | 264 |
| Failed, excluded entirely | 24 |
| Carrying a `judge_salvaged` marker | 0 |

`_reduce_samples` drops failed samples rather than folding them in as zeros, so
the 24 contributed nothing to any cell. No sample carries a salvage marker, so
`_salvage_scores` never produced a published number either. **No change to the
salvage path can move a number in the published table.** That statement is
stronger than the "24 of 24 recover" claim it replaces, and it is checkable
from these files alone.

Two limits on what this archive can support:

- **It cannot say how many of the 264 graded samples reached a score through
  `_extract_json_object`'s prefix path** rather than a clean whole-payload
  parse. That path was unmarked until the round 9 hardening added
  `judge_salvaged` to it. That gap is the reason the marker exists, and the
  reason no claim about tightening the parser can be validated here.
- **Re-walking the 24 failures is weaker than it looks.** Only 200 characters
  of each payload survive (#3975), so a re-parse exercises the stored prefix,
  not the payload the judge actually emitted. All 24 prefixes re-parse under
  the hardened salvage; that is consistency, not proof of recovery.

One number does transfer. Of the 264 graded samples, **none** has a `reasoning`
string naming a score field; the only 24 that do are the stored parse-error
strings, which are not judge prose. Refusing a payload whose prose names a
score field therefore costs nothing on observed output, which is what makes the
bare-identifier count affordable.

## Known limits

These runs carry the defects the procedure document lists. They are archived as
the evidence behind a specific conclusion, not as a clean dataset:

- Ambient user-level instructions were present in every cell.
- The Copilot provider injects treatment text into the user message, so this
  measures priming rather than always-on placement (issue #3934).
- The judge is the same model family being evaluated.
- Negative scenarios do not feed the verdict (issue #3933).
