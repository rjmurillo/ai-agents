# Extension Points

- **A new tier.** Add its row to the tier table and its branch to the tier-dispatch
  block in `SKILL.md`. `test_pr_merge_ready.py` owns the tier set, so the producer
  changes first and `tests/commands/test_pr_autofix_tier_contract.py` fails until
  `SKILL.md` agrees.
- **A new merge state.** Add a row to the merge-path table in `SKILL.md` and to the
  producer's supported set together. A state with no row in that table must stay UNSUPPORTED rather
  than fall through to a default; the test that pins that is deliberate.
- **A different round budget.** `check_pr_round_cap.py` owns both the count and the
  wall-clock budget. Change them there and every caller moves together.
- **A different concurrency boundary.** The Force-Push Safety SHA gate owns it.
  It is a hard gate (re-read the ref, pin `--force-with-lease` to the observed
  SHA), so a replacement has to be at least as strong; an advisory marker is not.
