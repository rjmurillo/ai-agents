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

# Eval rule activation (does the rule fire when conditions hold?):
python3 scripts/eval/eval-rule-activation.py \
  --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json --dry-run

# Detect pairwise skill overlap (are two skills redundant with each other?):
python3 scripts/eval/eval-skill-overlap.py \
  --pairs scripts/eval/examples/example-overlap-pairs.json --dry-run
```

## Scripts

| Script | Purpose | ADR |
|--------|---------|-----|
| `eval-suite.py` | Orchestrator. Detects changes, routes to correct evaluator. | ADR-023 + ADR-057 |
| `eval-prompt-change.py` | Before/after behavioral comparison for prompt changes. | ADR-057 |
| `eval-agents.py` | Agent definition quality assessment (standalone). | Complementary |
| `eval-knowledge-integration.py` | Skill context value measurement (baseline vs enhanced). | Complementary |
| `eval-skill-overlap.py` | Pairwise skill redundancy detection (DISTINCT / OVERLAP / SUBSUMED) for catalog pruning. | Complementary |
| `eval-rule-activation.py` | `.claude/rules/*.md` activation across baseline / description / full mechanisms. | Complementary |
| `analyze-pr-churn.py` | Deterministic commit-churn classification across a PR cohort (degenerate vs control) to evaluate instruction/rule changes against historical PRs. No LLM; core in `_pr_churn.py`. | Complementary |
| `eval-reviewer-asymmetry.py` | Statistical-significance test for `templates/agents/{critic,qa,implementer}.shared.md` reviewer-asymmetry framing. Fisher's exact (verdict-pass) + Mann-Whitney U (findings-count). | Complementary |
| `_anthropic_api.py` | Shared API utilities (key loading, API calls). | N/A |

## Reviewer-Asymmetry Eval

`eval-reviewer-asymmetry.py` measures whether the reviewer-asymmetry
framing in the new critic/qa/implementer templates produces a statistically
significant behavioral delta vs the origin/main control versions.

- **Control**: agent template at the chosen git ref (default: `main`).
- **Treatment**: agent template at HEAD (working copy).
- **Trials**: configurable, default 5; production runs use 10.
- **Tests**: Fisher's exact (one-sided) on verdict-pass rate; Mann-Whitney U
  (one-sided) on findings count where the fixture sets `min_findings_count`.
- **Acceptance**: p < 0.05 AND treatment > control, both overall and
  per-agent.

Fixtures live in `evals/reviewer-asymmetry-spike/fixtures/` and follow a
schema that pairs `verdict_options` with optional `min_findings_count` for
continuous metrics. See `evals/reviewer-asymmetry-spike/README.md`.

Cost: ~$0.60 USD for 10 trials × 6 fixtures × 2 conditions = 120 calls.

## Rule Activation Eval

`eval-rule-activation.py` measures whether a `.claude/rules/*.md` file actually
changes agent behavior across three loading mechanisms:

1. **baseline**. Empty system prompt (control).
2. **description**. Only the rule's frontmatter `description` is in the system prompt. Mimics an agent reading `.claude/rules/` and matching descriptions.
3. **full**. Entire rule body in the system prompt. Mimics `@import` from CLAUDE.md or `alwaysApply: true`.

Each scenario × mechanism produces a response that is graded by an LLM judge on
three 1-5 dimensions: `activation_score`, `citation_score`, `behavior_score`.
The eval passes when the best non-baseline mechanism averages ≥3.5 and beats
baseline by ≥0.5. Any judge/API failure forces verdict `FAIL_JUDGE_ERRORS`,
overriding the score-based gate. A scenarios file that contains no positive
cases (only `skip-rule-not-applicable` scenarios) yields `NO_POSITIVE_CASES`,
also a failing verdict because activation cannot be validated by negative
cases alone.

Per-rule scenario files live in `tests/evals/rule-scenarios/{rule}.json`:

```json
{
  "rule_path": ".claude/rules/working-with-legacy-code.md",
  "rule_id": "working-with-legacy-code",
  "scenarios": [
    {
      "id": "S1",
      "desc": "Refactor untested legacy function",
      "input": "Simulated user prompt that should trigger the rule.",
      "expected_signals": ["characterization", "tests before", "seam"],
      "expected_gate": "characterization-tests-first",
      "rationale": "Why the rule must activate here."
    },
    {
      "id": "Sn",
      "desc": "Negative case: well-tested recent code",
      "input": "...",
      "expected_signals": ["existing tests"],
      "expected_gate": "skip-rule-not-applicable",
      "rationale": "Rule should NOT fire."
    }
  ]
}
```

Adding a new rule eval:

1. Write `tests/evals/rule-scenarios/{rule-id}.json` with 3-5 positive scenarios and at least one negative case.
2. Run `python3 scripts/eval/eval-rule-activation.py --scenarios tests/evals/rule-scenarios/{rule-id}.json --dry-run` to confirm the script can parse the rule.
3. Run live (without `--dry-run`) to score. Cost is ~$0.25 per rule (24 calls × ~3500 tokens).
4. Iterate on the rule's `description` field until the `description` mechanism scores within 0.5 of `full`. That is the signal the rule is activatable from frontmatter alone.

## Skill Overlap Eval

`eval-skill-overlap.py` answers a question `eval-knowledge-integration.py`
cannot: are two skills redundant with each other? The knowledge-integration
eval measures a skill against the baseline LLM. The overlap eval measures one
skill against its sibling, so the catalog prune has the second signal it needs.

For each pair `(A, B)` and each prompt, three conditions run: `baseline`
(prompt only), `skill_A` (prompt + A's context), and `skill_B` (prompt + B's
context). An LLM judge scores each response 1-5 against the prompt's expected
answer. The per-direction deltas drive the verdict:

- **DISTINCT**: each skill helps mainly on its own prompts. Keep both.
- **OVERLAP**: both skills cover each other's prompts symmetrically. Fold candidate.
- **SUBSUMED**: one skill covers the other's prompts without reciprocity. Prune candidate.

Phase 1 (Issue #1932) is **explicit pair list only**. No cluster shortcuts, no
full N-squared sweep. The N-squared cost is `N^2 * prompts * 3 conditions *
judge` (~36k calls for 70 skills), so unbounded mode is gated out of scope.

Input is a `cluster.json` with a `pairs` list and a `prompts` map. See
`examples/example-overlap-pairs.json`. The default run cost estimate prints at
run start (API call count, token total, USD estimate).

Dry-run validates the pair file, referenced skill directories, and `--run-id`
before printing the cost estimate. `--run-id` accepts 1-128 characters: letters,
digits, `.`, `_`, and `-`; it must start with a letter or digit and cannot
contain `..`. Pair entries must reference two different skills. Judge responses
that are not valid `{"score": <number>}` payloads fail the run with exit code 3
instead of being averaged into a verdict.

Output lands at `evals/reports/overlap-<RUNID>/`: `matrix.json` (machine
readable per-pair deltas and verdicts) and `REPORT.md` (prune/fold table).

Note on the Issue #1932 Phase 1 pairs: `doc-coverage`, `doc-sync`, and
`session-qa-eligibility` were deleted in the M1 catalog prune (commit
`5c4729345`, #1942). Three of the four named pairs referenced those skills, so
the example file targets the surviving overlapping pairs only
(`memory-enhancement`/`curating-memories`,
`curating-memories`/`exploring-knowledge-graph`).

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
| `--pairs FILE` | eval-skill-overlap | cluster.json with explicit `[skillA, skillB]` pairs and prompts |
| `--run-id ID` | eval-skill-overlap | Override the report directory name (`overlap-<ID>`) |

## Environment

Set `ANTHROPIC_API_KEY` as an environment variable. The scripts also check `.env` files as a fallback.

## References

- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md)
- [ADR-023](.agents/architecture/ADR-023-quality-gate-prompt-testing.md)
- [Methodology](.agents/testing/prompt-eval-methodology.md)
