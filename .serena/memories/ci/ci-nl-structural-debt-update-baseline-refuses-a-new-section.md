# check_nl_structural_debt --update-baseline refuses to seed a new baseline section

## What happens

`--update-baseline` does not write when the measurement shows growth. In `scripts/validation/check_nl_structural_debt.py`, `run()` calls `compare()` and returns 1 on any growth before it reaches the write at the end of the function (lines 318 to 341).

`compare()` (lines 226 to 248) counts a section as growth when:

- a `cardinality` key is missing from the baseline, or
- a `duplicate_blocks` key exceeds its baseline value, where a missing key allows 0.

So a brand-new section always looks like growth, and the flag that should record it refuses.

## What works

Write the new section into `scripts/validation/nl_structural_debt_baseline.json` directly (sorted keys, 2-space indent, trailing newline, the format `run()` writes). Then run the check to confirm exit 0. The flag still works for shrink and for re-recording when nothing grew.

## Other refusal

The flag also exits 2 when the working directory is outside the target checkout (`_refuses_write_from_outside`, lines 284 to 301). Run it from inside the checkout it will write.

## Sources

- `scripts/validation/check_nl_structural_debt.py` lines 226 to 248, 284 to 341.
