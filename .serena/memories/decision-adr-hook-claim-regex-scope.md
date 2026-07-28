# The ADR hook-claim regex is deliberately narrow, and the narrowing is free

## Question

`tests/hooks/test_adr_hook_claims.py` uses `_HOOK_PATH_RE` to find ADR table
rows claiming a hook is implemented. The pattern requires an `invoke_` filename
prefix and at least one leading directory segment. Should it be widened to any
`.py` under a hooks directory?

## Conventional answer

Widen it. A narrower pattern means less coverage, and shared machinery such as
`.claude/hooks/_dispatch.py` can go stale in an ADR just as easily as an
`invoke_*` hook can.

## First-principles position

No. `invoke_*` under an event directory is the shape the hook purges delete
(#3184, #3349, #3295), so it is the shape an ADR can go stale about. Shared
machinery is not purged; it is refactored, and a refactor updates its callers.
Widening buys coverage of a failure mode that has not occurred.

## Evidence

Measured, not assumed. Ran a wide regex (`` `[^`]*hooks/[\w./-]+\.py` ``)
across every ADR table row that marks a hook implemented and is not retired,
then subtracted the current pattern's matches:

```
claim rows a wider regex would catch but the current one misses: 0
```

Also probed the pattern directly. It does match
`.claude/hooks/invoke_dispatch_claude.py` (a review comment on PR #3397 claimed
otherwise; the claim was wrong). It does not match a bare `invoke_x.py` with no
directory segment, nor `.claude/hooks/_dispatch.py`.

## Decision

Left the pattern alone. The comment above it on `main` (shipped in #3397) now
describes the shape accurately. Do not widen without first re-running the
measurement above and finding a nonzero result.

Refs #3373, PR #3397.
