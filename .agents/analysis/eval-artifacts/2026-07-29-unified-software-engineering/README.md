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

Verified 2026-07-29 under the structure-aware parser: 24 of 24 failed samples
recover and every cell reproduces to two decimals.

## Known limits

These runs carry the defects the procedure document lists. They are archived as
the evidence behind a specific conclusion, not as a clean dataset:

- Ambient user-level instructions were present in every cell.
- The Copilot provider injects treatment text into the user message, so this
  measures priming rather than always-on placement (issue #3934).
- The judge is the same model family being evaluated.
- Negative scenarios do not feed the verdict (issue #3933).
