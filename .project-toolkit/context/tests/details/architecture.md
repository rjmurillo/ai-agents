## Architecture

- `tests/evals/`: ADR-057 corpora & `scripts/eval/` tests. `evals/`: ADR-058 agent-vs-baseline (not pytest); `evals/skill-rewrites/`: ADR-127 evidence.
- Deliberate zero-collection modules carry `pytest-zero-collection:`; `pytest-zero-collection-conditional: <reason>` covers collection-time skips.
