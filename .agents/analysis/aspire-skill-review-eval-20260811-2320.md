# Aspire Skill Review Eval (TASK-022)

Behavioral prompt-change eval for the SkillForge external-skill-source
adaptation guardrail. Sanitized summary; raw per-run model output is not
committed (kept only under gitignored `.agents/scratch/`).

## Run metadata

| Field | Value |
|---|---|
| Run ID | `20260811-2320` |
| Eval type | prompt-change (ADR-057) |
| Provider | copilot |
| Model | `claude-opus-5` |
| Source | `git: origin/main:.claude/skills/SkillForge/SKILL.md -> working copy` |
| Changed skill | `.claude/skills/SkillForge/SKILL.md` |
| Scenarios | `tests/evals/skills/aspire-skill-review-scenarios.json` |
| Base ref | `origin/main` |
| Aspire source commit | `d1c7add665f7e6582cdaa1b328c44172f0f96339` |
| Runs per scenario | 3 |
| Security-critical | False |

## Acceptance gate

**Verdict: PASS**

| Criterion | Result |
|---|---|
| no_regression | PASS |
| has_improvement | PASS (informational, non-gating) |
| no_unexplained_regressions | PASS |
| no_high_flakiness | PASS |

- Before score: 100%
- After score: 100%
- Delta: +0%
- has_improvement: True (informational)
- Improvements: none
- Regressions: none
- Flaky scenarios: none
- High-flakiness scenarios: none
- API calls: 30, estimated tokens: 105000

## Per-scenario summary

| Scenario | Before pass rate | After pass rate | Flaky (after) |
|---|---|---|---|
| `S1-positive-reuse` | 100% (3/3) | 100% (3/3) | False |
| `S2-negative-duplicate-creation` | 100% (3/3) | 100% (3/3) | False |
| `S3-negative-missing-source-identity` | 100% (3/3) | 100% (3/3) | False |
| `S4-edge-product-specific-rejection` | 100% (3/3) | 100% (3/3) | False |
| `S5-positive-create-when-no-owner` | 100% (3/3) | 100% (3/3) | False |

## Coverage

- Positive: `S1-positive-reuse`, `S5-positive-create-when-no-owner`
- Negative (duplicate creation): `S2-negative-duplicate-creation`
- Negative (missing source identity): `S3-negative-missing-source-identity`
- Edge (product-specific rejection): `S4-edge-product-specific-rejection`

All four required scenario types plus one over-rejection guard are present.
The gate returned PASS with no regression and no high flakiness.

