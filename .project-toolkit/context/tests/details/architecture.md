## Architecture

- `tests/evals/`: ADR-057 corpora and `scripts/eval/` runner tests. `evals/`: ADR-058 agent-vs-baseline, not pytest input; `evals/skill-rewrites/`: ADR-127 evidence.
- A deliberate zero-collection module carries `pytest-zero-collection:`; `pytest-zero-collection-conditional: <reason>` covers a collection-time skip, honored only where it happened.
