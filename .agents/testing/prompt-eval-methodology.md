# Prompt Eval Methodology

Status: active
Version: 1.0.0
Date: 2026-04-19
Related: [ADR-023](../architecture/ADR-023-quality-gate-prompt-testing.md), [testing-approach.md](../steering/testing-approach.md)

## Purpose

This document defines how to validate prompt changes for behavioral correctness. It complements [ADR-023](../architecture/ADR-023-quality-gate-prompt-testing.md), which covers structural validation only.

Structural tests prove a prompt has the right sections. They do not prove the LLM interprets the prompt correctly. Behavioral evals close that gap.

## When to Use Which Approach

| Need | Use | Location | Speed | Determinism |
|------|-----|----------|-------|-------------|
| Required sections, format, terminology | Structural tests (ADR-023) | `tests/*.Tests.ps1` | Fast (seconds) | Deterministic |
| LLM interpretation, verdict correctness, regression proof | Behavioral evals (this doc) | `.agents/security/benchmarks/` or `tests/evals/` | Slow (minutes, API cost) | Probabilistic |

Rule of thumb:

- If the change alters text structure (sections added, renamed, moved), run structural tests.
- If the change alters instructions (thresholds, stop conditions, fallback rules, routing logic), run behavioral evals.
- A change that does both needs both.

## Pattern

Scenario-based LLM judgment. Each scenario names an input condition and the expected verdict. Run the prompt against every scenario before and after the change. Compare deltas.

### Minimum Scenario Shape

```python
SCENARIOS = [
    {
        "id": "S1",
        "desc": "Memory Phase skipped when budget exhausted",
        "input": "...prompt context and simulated state...",
        "expected_verdict": "SKIP_PHASE",
        "expected_reason_contains": "budget",
        "rationale": "Stop condition fires before Memory Phase runs",
    },
    # ...
]
```

### Runner Skeleton

```python
from pathlib import Path

BEFORE = Path(".agents/.../prompt.md").read_text()
AFTER  = Path(".agents/.../prompt.md.after").read_text()

def judge_scenario(prompt_text: str, scenario: dict) -> dict:
    """Invoke the LLM with prompt_text + scenario.input, return parsed verdict.

    Implementations:
    - Use Task tool (subagent_type matching the prompt's agent), or
    - Call the Anthropic API directly with the prompt as system message.

    Return: {"verdict": str, "reason": str, "raw": str}
    """
    ...

def score(results, scenarios):
    passed = 0
    for r, s in zip(results, scenarios):
        if r["verdict"] == s["expected_verdict"] and s["expected_reason_contains"] in r["reason"]:
            passed += 1
    return passed / len(scenarios)

before_results = [judge_scenario(BEFORE, s) for s in SCENARIOS]
after_results  = [judge_scenario(AFTER,  s) for s in SCENARIOS]

before_score = score(before_results, SCENARIOS)
after_score  = score(after_results,  SCENARIOS)
delta = after_score - before_score

print(f"Before: {before_score:.0%}  After: {after_score:.0%}  Delta: {delta:+.0%}")
```

### Acceptance Gate

A prompt change is acceptable when all three hold:

1. `after_score >= before_score` (no regression on existing scenarios).
2. Any scenario the change targets moves from fail to pass.
3. No scenario flips from pass to fail without explicit justification in the PR.

Record the scores in the PR description. Store scenarios under version control so future changes can rerun the baseline.

## Worked Example: Issue #1686 (Stop Conditions in research.md)

Issue #1686 added budget, fallback rules, and stop conditions to `.claude/commands/research.md`. The first draft regressed behavior by 20 percentage points. Eval-driven iteration arrived at a final +20pp improvement (60 percent to 80 percent on five scenarios).

Scenarios tested:

| ID | Condition | Expected |
|----|-----------|----------|
| S1 | All five phases complete | STOP, reason contains "all phases" |
| S2 | Three phases failed | STOP, reason contains "failure threshold" |
| S3 | 50k token budget reached mid-phase | STOP, reason contains "budget" |
| S4 | WebSearch returns zero results | FALLBACK to memory search |
| S5 | Serena and Forgetful both unavailable | FALLBACK to web search, log degradation |

Without these scenarios, the initial regression (ambiguous budget wording caused the LLM to stop too early) would have shipped. The evals caught it before merge.

## Template Location

Use `.agents/security/benchmarks/test_agent_review_quality.py` as the scenario-based template. It documents the shape even though the test cases are currently skipped (pending Task tool integration). Copy its structure for new behavioral eval suites.

## Minimum Cadence

Run evals:

- Before merging any prompt change that touches instructions, thresholds, or decision logic.
- On a monthly schedule for prompts under active iteration, to catch model drift.
- After any Anthropic model version bump, to catch interpretation shifts.

## References

- [ADR-023](../architecture/ADR-023-quality-gate-prompt-testing.md): Structural validation for quality gate prompts. Behavioral evals are the complement, not a replacement.
- [Issue #1686](https://github.com/rjmurillo/ai-agents/issues/1686): Stop-condition fix that motivated this methodology.
- [Issue #1688](https://github.com/rjmurillo/ai-agents/issues/1688): Source issue for this document.
- [.agents/security/benchmarks/test_agent_review_quality.py](../security/benchmarks/test_agent_review_quality.py): Scenario-based test template.
- [.agents/steering/testing-approach.md](../steering/testing-approach.md): Pester testing conventions, cross-referenced from this doc.
