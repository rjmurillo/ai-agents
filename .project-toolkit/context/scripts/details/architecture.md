## Architecture

- `_SEQUENCE`: a tuple of `_Gate(name, run, skip_when_quick, already_run_by, ci_owned_by, notes)` read by one loop, so adding a gate is one line. `--quick` skips `skip_when_quick` rows; `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1` from `lefthook.yml` skips the `already_run_by` and `ci_owned_by` rows, so a push run is not the full sequence.
- `scripts/workflows/`: Actions step helpers.
