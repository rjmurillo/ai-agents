## Architecture

- `tests/evals/` is ADR-057 prompt-regression corpora plus tests of its `scripts/eval/` runners; top-level `evals/` is ADR-058 agent-vs-baseline, not pytest input.
- A deliberate zero-collection module carries `pytest-zero-collection:`; `pytest-zero-collection-conditional: <reason>` covers a collection-time skip, honored only where it happened.
