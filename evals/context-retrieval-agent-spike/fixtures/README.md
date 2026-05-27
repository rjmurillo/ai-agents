# context-retrieval-Agent-Spike Fixture Corpus

A/B corpus for the `context-retrieval` agent. Empty scaffold.

## Authoring rules

- Synthetic or paraphrased-from-public only. No real credentials, secrets, customer data, employee names, or verbatim production code.
- Fixture IDs `F001`, `F002`, ... stable order; never renumber; append only.
- One verdict per fixture from `verdict_options`.
- ≥30% agent-discriminating per REQ-004 AC-5.

## Verdict distribution

(populated when fixtures land)

| Verdict | Fixtures | Count |
|---|---|---|
| _TBA_ | _TBA_ | 0 |

## Per-fixture rationale

(populated when fixtures land)

| Fixture | Provenance | Verdict | Why this fixture discriminates treatment from control |
|---|---|---|---|
| _TBA_ | _TBA_ | _TBA_ | _TBA_ |

## A/B configuration

Default control = `origin/main`, treatment = `HEAD`. Override in the runner invocation if comparing other axes (see parent README).

## Cross-references

- `evals/context-retrieval-agent-spike/README.md`. Spike rationale + authoring guide.
- `evals/reviewer-asymmetry-spike/fixtures/`. Reference implementation.
