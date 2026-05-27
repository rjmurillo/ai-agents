# decision-critic-Spike Fixture Corpus

Held-out corpus driving `scripts/eval/eval-agent-vs-baseline.py` against the `decision-critic` skill.

## Status

Empty. The scaffold creates the directory shape; fixture authoring is owned by the operator landing the first live run.

## Authoring rules

- Every fixture MUST be `synthetic` or `paraphrased-from-public`. No real credentials, no real third-party secrets, no real customer data, no real employee names, no verbatim production code.
- Fixture IDs are `F001`, `F002`, ... in stable order. Once landed, never renumber. Append only.
- Each fixture covers exactly one verdict in `verdict_options`. Distribution across verdicts SHOULD be documented in the per-fixture table below once fixtures exist.
- At least 30% of fixtures SHOULD be **agent-discriminating** per REQ-004 AC-5: cases where the naive baseline cannot answer correctly without the skill's knowledge.

## Verdict distribution

(populated when fixtures land)

| Verdict | Fixtures | Count |
|---|---|---|
| _TBA_ | _TBA_ | 0 |

## Per-fixture rationale

(populated when fixtures land)

| Fixture | Provenance | Verdict | Why this fixture distinguishes the agent |
|---|---|---|---|
| _TBA_ | _TBA_ | _TBA_ | _TBA_ |

## Cross-references

- `evals/decision-critic-spike/README.md`. Spike rationale and authoring guide.
- `evals/security-spike/fixtures/README.md`. Reference implementation of the per-fixture table format.
