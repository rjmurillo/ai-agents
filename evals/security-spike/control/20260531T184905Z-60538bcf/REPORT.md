# Variance Control Report: F002 / security

- Run ID: `20260531T184905Z-60538bcf`
- Model: `claude-sonnet-4-6`
- Reps: 20 (answered 20, error 0)

## Finding

text-varies-verdict-stable: the API has output-text non-determinism but the scorer is robust. Gate AC-10 on verdict variance, not text variance.

## Verdict variance

- Distribution: ESCALATE=20
- Distinct verdicts: 1 (stable: True)
- Modal: ESCALATE x20

## Pass-rate variance

- Expected: IDENTIFY
- Pass rate: 0.000 (0/20)
- Pass variance: 0.0000 (any fail: True)

## Response-text variance

- Unique responses: 20/20 (all identical: False)
- Mean consecutive normalized edit distance: 0.6358
- Max consecutive normalized edit distance: 0.7862
