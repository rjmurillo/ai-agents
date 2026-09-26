## Architecture

- `_SEQUENCE`: a tuple of `_Gate(name, run, skip_when_quick, already_run_by, notes)` read by one loop, so adding a gate is one line. `--quick` skips `skip_when_quick` rows; `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1` from `lefthook.yml` skips the five `already_run_by` rows, so a push run is not the full sequence.
- `scripts/workflow/` (singular): agent pipeline executor. `scripts/workflows/` (plural): Actions step helpers. Unrelated.
