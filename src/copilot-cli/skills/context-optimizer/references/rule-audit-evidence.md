# Rule Audit Evidence: the 2026-07-29 unified-software-engineering run

Companion to `rule-audit-procedure.md`. That document defines the procedure.
This file records the forensic lessons without preserving a volatile result
snapshot. Read it before relying on an archived judge result or writing a new
instrument that parses judge output.

Raw artifacts: `.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/`.

## What recovery established

An earlier result table treated every cell as fully graded. That was false.
Some judge output was discarded, and the loss was concentrated in the Opus
artifacts rather than distributed evenly across model families. The missing
payloads were recovered from Copilot CLI transcripts.

The recovery exposed two separate populations. The stored prefixes were
truncated and could mislead the parser diagnosis. The full transcript payloads
showed malformed JSON at the point where the prefix had ended. Do not infer a
root cause from a truncated preview when the full response exists elsewhere.

Attribution also required care. Matching a recovered payload to a published
cell by its score is circular. The judge input contains the response being
graded, so that input is the authoritative join key. Score-based matching can
assign the right-looking payload to the wrong cell.

Replaying the current parser against the recovered records separated parser
divergence from ordinary judge output. The recovery preserved each archived
request, response, and verdict exactly. It did not turn post-hoc recovery into
independent replication.

## What remains uncertain

The extractor was written after the failed records were known. That makes the
recovery post-hoc. Recovering every available failure avoids selecting only
the records that support the conclusion, but it does not create a fresh audit.

The archive is evidence about that historical run. It is not a permanent
benchmark, a current model comparison, or a current context-size claim. Run a
new audit from the current tree when the decision matters.

## Lessons for future instruments

- Name the population before stating a result. A detector can be correct over
  the wrong population and still support a false conclusion.
- Preserve the full judge payload when the result may need forensic recovery.
  A truncated preview can explain a parser error incorrectly.
- Join records using the graded input, not the score produced by parsing it.
- Mark incomplete, malformed, and recovered records explicitly. Never replace
  a missing observation with zero or a guessed value.
- Keep historical evidence separate from active policy. Do not copy a result
  snapshot into an active rule or skill.

The detailed parser history remains in
`rule-audit-parser-forensics.md`. The measurement failure patterns remain in
`rule-audit-measurement-discipline.md`.

<!-- vendor-portability: declared. This file cites
.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the
archive holding the forensic records. It is a narrative citation, not a path
the skill reads or writes. A vendored install loses local access to that
archive, but the guidance remains useful. Issue #2050. -->
