# Eval Scripts

Behavioral evaluation tools for prompt, skill, and agent changes. Implements ADR-057.

## Quick Start

```bash
# Auto-detect changes and run appropriate evals:
python3 scripts/eval/eval-suite.py --dry-run

# Evaluate a specific prompt change (before/after comparison):
python3 scripts/eval/eval-prompt-change.py \
  --prompt .claude/commands/research.md \
  --scenarios tests/evals/research-scenarios.json \
  --base-ref main \
  --dry-run

# Assess agent definition quality:
python3 scripts/eval/eval-agents.py --agent analyst --dry-run

# Assess skill knowledge integration:
python3 scripts/eval/eval-knowledge-integration.py --skill cva-analysis --dry-run
```

## Scripts

| Script | Purpose | ADR |
|--------|---------|-----|
| `eval-suite.py` | Orchestrator. Detects changes, routes to correct evaluator. | ADR-023 + ADR-057 |
| `eval-prompt-change.py` | Before/after behavioral comparison for prompt changes. | ADR-057 |
| `eval-agents.py` | Agent definition quality assessment (standalone). | Complementary |
| `eval-knowledge-integration.py` | Skill context value measurement (baseline vs enhanced). | Complementary |
| `_anthropic_api.py` | Shared API utilities (key loading, API calls). | N/A |

## Scenario File Format

See `examples/example-scenarios.json` for a working template.

```json
{
  "scenarios": [
    {
      "id": "S1",
      "desc": "What this scenario tests",
      "input": "Simulated context the LLM receives",
      "expected_verdict": "STOP",
      "expected_reason_contains": "budget",
      "rationale": "Why this is the expected behavior"
    }
  ]
}
```

Required fields: `id`, `desc`, `input`, `expected_verdict`.
Optional: `expected_reason_contains`, `rationale`.

## Scenario File Locations

| Prompt Type | Scenario Location |
|-------------|-------------------|
| Security benchmarks | `.agents/security/benchmarks/` |
| Other prompt evals | `tests/evals/` |

Convention: for a prompt at `path/to/name.md`, name the scenario file `name-scenarios.json`.

## Flags

All scripts support `--dry-run` (validate inputs, no API calls) and `--output FILE` (write JSON results).

| Flag | Scripts | Purpose |
|------|---------|---------|
| `--dry-run` | All | Validate without API calls |
| `--runs N` | eval-agents, eval-knowledge-integration | Multi-run flakiness detection |
| `--security-critical` | eval-prompt-change | 5 runs, 100% pass required |
| `--base-ref REF` | eval-prompt-change, eval-suite | Git ref for comparison (default: main) |
| `--scope` | eval-suite | Limit to prompts, agents, or skills |

## Environment

Set `ANTHROPIC_API_KEY` as an environment variable. The scripts also check `.env` files as a fallback.

## References

- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md)
- [ADR-023](.agents/architecture/ADR-023-quality-gate-prompt-testing.md)
- [Methodology](.agents/testing/prompt-eval-methodology.md)
