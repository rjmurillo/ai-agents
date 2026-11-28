# The eval runner's flat 3,500 tokens per call undercounts cost on large prompts

**Atomicity**: 90%
**Category**: Eval cost accounting
**Source**: Agent session sweep, sessions dated 2026-10. Sweep ids E079. State checked on main at 1be533c496 (2026-11-26).

## Question

Can the eval runner's ledger cost line be trusted against a spend cap?

## Conventional answer

The runner's ledger cost line was trusted as the eval budget measure against the $20 cap (ADR-057 eval runner).

## First-principles position

The runner estimates a flat 3,500 tokens per call. A skillforge rerun used an estimated 45,000 input tokens per call. The runner reported about 168,000 tokens in total across 48 calls. The estimate based on prompt length put spend above the ledger figure.

## Evidence with limits

- ADR-057 skillforge rerun on 2026-10-31: a 181,000-character prompt, about 45,000 input tokens per call, 48 calls.
- The runner printed a flat 3,500 tokens per call, about 168,000 in total. The skillforge prompt alone costs about $4.4.
- Estimated real spend was about $16.5 against about $11 on the ledger.
- Quote: "The runner's own line says ~168,000 tokens; that is a flat 3,500 per call and undercounts this large prompt."
- Limits: Real spend is an agent estimate from characters over four and list price, not metered usage. One run on one prompt, 2026-10-31.
- State on main at 1be533c496 (2026-11-26): still wrong. `scripts/eval/_eval_common.py:24` sets `EST_TOKENS_PER_CALL = 3500` with a midpoint comment.

## Decision

Do not read the runner's cost line as spend for large prompts. Estimate from prompt length, or read API usage, before checking a budget cap.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/eval-harness-observations.md`
