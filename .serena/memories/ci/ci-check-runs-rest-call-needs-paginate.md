# REST check-runs lists need --paginate, or a passing required check looks missing

## What happened

A PR head here carries well over 100 check-runs. On PR #6316 head 377681a14 (2026-10-12), `total_count` was 153. A plain `gh api repos/rjmurillo/ai-agents/commits/<sha>/check-runs` returned 30 runs (the default page size). With `--paginate` the pages returned 100 and 53.

The coordinator also reported 162 runs on commit 26afd5b0d. Reading only page 1 there made a passing required check look missing.

## Rule of thumb

Always pass `--paginate` to the check-runs call when judging "all required checks passed". Compare `total_count` with the number of runs you read. A required name absent from a partial read proves nothing.

## Sources

- Measured on PR #6316 with the commands above.
- The 162-run figure is a coordinator report, not re-measured.
